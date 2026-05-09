from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from sfa.domain.enrichment_ports import PlayerEnrichDTO
from sfa.domain.ingestion_ports import FixtureEventRawDTO
from sfa.domain.raw_data_ports import RawDataRepositoryPort, RawPlayerStatsDTO
from sfa.infrastructure.models.competitions.models import CompetitionStage
from sfa.infrastructure.models.enums import EventType
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.fixtures.models import Fixture
from sfa.infrastructure.models.player_stats.models import PlayerStats
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.standings.models import StandingSnapshot
from sfa.infrastructure.models.teams.models import Team

logger = logging.getLogger(__name__)


class RawDataRepository(RawDataRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_raw_stats_for_calculation(
        self,
        competition_id: int,
        season: str,
        player_ids: list[int] | None = None,
    ) -> list[RawPlayerStatsDTO]:
        HomeStanding = aliased(StandingSnapshot)
        AwayStanding = aliased(StandingSnapshot)
        HomeTeam = aliased(Team)

        # Use the latest matchday available for standings in this competition/season
        max_matchday_sq = (
            select(func.max(StandingSnapshot.matchday))
            .where(
                StandingSnapshot.competition_id == competition_id,
                StandingSnapshot.season == season,
            )
            .scalar_subquery()
        )

        stmt = (
            select(
                PlayerStats.player_id,
                PlayerStats.fixture_id,
                PlayerStats.season,
                PlayerStats.goals,
                PlayerStats.assists,
                PlayerStats.shots_on,
                PlayerStats.passes_key,
                PlayerStats.dribbles_won.label("dribbles_success"),
                PlayerStats.duels_won,
                PlayerStats.tackles_won.label("tackles"),
                PlayerStats.interceptions,
                PlayerStats.blocks,
                PlayerStats.minutes,
                Player.name.label("player_name"),
                Player.position.label("player_position"),
                Player.team_id.label("player_team_id"),
                Fixture.competition_id.label("competition_id"),
                Fixture.home_team_id,
                Fixture.away_team_id,
                HomeTeam.external_id.label("home_team_ext_id"),
                func.coalesce(CompetitionStage.stage_factor, 1.0).label("stage_factor"),
                func.coalesce(HomeStanding.position, 10).label("home_position"),
                func.coalesce(AwayStanding.position, 10).label("away_position"),
            )
            .join(Fixture, PlayerStats.fixture_id == Fixture.id)
            .join(Player, PlayerStats.player_id == Player.id)
            .join(HomeTeam, Fixture.home_team_id == HomeTeam.id)
            .outerjoin(
                CompetitionStage,
                and_(
                    CompetitionStage.competition_id == competition_id,
                    CompetitionStage.stage == Fixture.stage,
                ),
            )
            .outerjoin(
                HomeStanding,
                and_(
                    HomeStanding.team_id == Fixture.home_team_id,
                    HomeStanding.competition_id == competition_id,
                    HomeStanding.season == season,
                    HomeStanding.matchday == max_matchday_sq,
                ),
            )
            .outerjoin(
                AwayStanding,
                and_(
                    AwayStanding.team_id == Fixture.away_team_id,
                    AwayStanding.competition_id == competition_id,
                    AwayStanding.season == season,
                    AwayStanding.matchday == max_matchday_sq,
                ),
            )
            .where(
                Fixture.competition_id == competition_id,
                PlayerStats.season == season,
            )
        )

        if player_ids:
            stmt = stmt.where(PlayerStats.player_id.in_(player_ids))

        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []

        # Batch-load fixture events to avoid N+1
        fixture_ids = {row.fixture_id for row in rows}
        events_by_fixture = await self._get_events_batch(fixture_ids)

        result: list[RawPlayerStatsDTO] = []
        for row in rows:
            is_away = row.player_team_id == row.away_team_id
            player_team_pos = int(row.away_position if is_away else row.home_position)
            rival_pos = int(row.home_position if is_away else row.away_position)

            result.append(
                RawPlayerStatsDTO(
                    player_id=row.player_id,
                    fixture_id=row.fixture_id,
                    competition_id=row.competition_id,
                    season=row.season,
                    player_name=row.player_name,
                    position=row.player_position,
                    goals=row.goals,
                    assists=row.assists,
                    shots_on=row.shots_on,
                    passes_key=row.passes_key,
                    dribbles_success=row.dribbles_success,
                    duels_won=row.duels_won,
                    tackles=row.tackles,
                    interceptions=row.interceptions,
                    blocks=row.blocks,
                    minutes=row.minutes,
                    is_away=is_away,
                    rival_position=rival_pos,
                    player_team_position=player_team_pos,
                    stage_factor=float(row.stage_factor),
                    home_team_external_id=row.home_team_ext_id or 0,
                    fixture_events=events_by_fixture.get(row.fixture_id, []),
                )
            )
        return result

    async def get_fixture_events_raw(self, fixture_id: int) -> list[FixtureEventRawDTO]:
        # NOTE: FixtureEventRawDTO fields cannot be fully reconstructed from player_events because:
        # - Only events for tracked players are stored (goals by opponents may be missing)
        # - extra_minute is not stored; defaults to 0
        # - assist_name is matched by minute, which may collide for multi-goal minutes
        # These limitations affect score-at-minute accuracy for M3 when opponents scored.

        goal_stmt = (
            select(
                PlayerEvent.minute,
                PlayerEvent.event_type,
                Player.name.label("player_name"),
                Team.external_id.label("team_ext_id"),
            )
            .join(Player, PlayerEvent.player_id == Player.id)
            .join(Team, Player.team_id == Team.id)
            .where(
                PlayerEvent.fixture_id == fixture_id,
                PlayerEvent.event_type.in_([EventType.GOAL, EventType.GOAL_PENALTY]),
            )
            .order_by(PlayerEvent.minute)
        )

        assist_stmt = (
            select(
                PlayerEvent.minute,
                PlayerEvent.event_type,
                Player.name.label("assister_name"),
            )
            .join(Player, PlayerEvent.player_id == Player.id)
            .where(
                PlayerEvent.fixture_id == fixture_id,
                PlayerEvent.event_type.in_([EventType.ASSIST, EventType.CORNER_ASSIST]),
            )
        )

        goal_rows = (await self._session.execute(goal_stmt)).all()
        assist_rows = (await self._session.execute(assist_stmt)).all()

        assist_by_minute: dict[int, tuple[str, EventType]] = {}
        for a in assist_rows:
            assist_by_minute[a.minute] = (a.assister_name, a.event_type)

        events: list[FixtureEventRawDTO] = []
        for g in goal_rows:
            detail = "Penalty" if g.event_type == EventType.GOAL_PENALTY else ""
            assist_info = assist_by_minute.get(g.minute)
            assist_name = assist_info[0] if assist_info else None
            if assist_info and assist_info[1] == EventType.CORNER_ASSIST:
                detail = detail or "Corner Kicked"

            events.append(
                FixtureEventRawDTO(
                    type="Goal",
                    detail=detail,
                    player_name=g.player_name,
                    assist_name=assist_name,
                    team_external_id=g.team_ext_id or 0,
                    minute=g.minute,
                    extra_minute=0,
                )
            )
        return events

    async def get_downloaded_fixture_ids(
        self, competition_id: int, season: str,
    ) -> set[int]:
        stmt = (
            select(PlayerStats.fixture_id)
            .join(Fixture, PlayerStats.fixture_id == Fixture.id)
            .where(
                Fixture.competition_id == competition_id,
                PlayerStats.season == season,
            )
            .distinct()
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return set(rows)

    async def get_players_in_competition(
        self, competition_id: int, season: str,
    ) -> list[PlayerEnrichDTO]:
        stmt = (
            select(
                Player.id,
                Player.name,
                Player.external_id,
                Player.fbref_id,
                Player.understat_id,
            )
            .join(PlayerStats, PlayerStats.player_id == Player.id)
            .join(Fixture, PlayerStats.fixture_id == Fixture.id)
            .where(
                Fixture.competition_id == competition_id,
                PlayerStats.season == season,
            )
            .distinct()
            .order_by(Player.name)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            PlayerEnrichDTO(
                id=row.id,
                name=row.name,
                external_id=row.external_id,
                fbref_id=row.fbref_id,
                understat_id=row.understat_id,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_events_batch(
        self, fixture_ids: set[int],
    ) -> dict[int, list[FixtureEventRawDTO]]:
        if not fixture_ids:
            return {}

        goal_stmt = (
            select(
                PlayerEvent.fixture_id,
                PlayerEvent.minute,
                PlayerEvent.event_type,
                Player.name.label("player_name"),
                Team.external_id.label("team_ext_id"),
            )
            .join(Player, PlayerEvent.player_id == Player.id)
            .join(Team, Player.team_id == Team.id)
            .where(
                PlayerEvent.fixture_id.in_(fixture_ids),
                PlayerEvent.event_type.in_([EventType.GOAL, EventType.GOAL_PENALTY]),
            )
            .order_by(PlayerEvent.fixture_id, PlayerEvent.minute)
        )

        assist_stmt = (
            select(
                PlayerEvent.fixture_id,
                PlayerEvent.minute,
                PlayerEvent.event_type,
                Player.name.label("assister_name"),
            )
            .join(Player, PlayerEvent.player_id == Player.id)
            .where(
                PlayerEvent.fixture_id.in_(fixture_ids),
                PlayerEvent.event_type.in_([EventType.ASSIST, EventType.CORNER_ASSIST]),
            )
        )

        goal_rows = (await self._session.execute(goal_stmt)).all()
        assist_rows = (await self._session.execute(assist_stmt)).all()

        # assists keyed by (fixture_id, minute)
        assist_map: dict[tuple[int, int], tuple[str, EventType]] = {}
        for a in assist_rows:
            assist_map[(a.fixture_id, a.minute)] = (a.assister_name, a.event_type)

        result: dict[int, list[FixtureEventRawDTO]] = defaultdict(list)
        for g in goal_rows:
            detail = "Penalty" if g.event_type == EventType.GOAL_PENALTY else ""
            assist_info = assist_map.get((g.fixture_id, g.minute))
            assist_name = assist_info[0] if assist_info else None
            if assist_info and assist_info[1] == EventType.CORNER_ASSIST:
                detail = detail or "Corner Kicked"

            result[g.fixture_id].append(
                FixtureEventRawDTO(
                    type="Goal",
                    detail=detail,
                    player_name=g.player_name,
                    assist_name=assist_name,
                    team_external_id=g.team_ext_id or 0,
                    minute=g.minute,
                    extra_minute=0,
                )
            )
        return dict(result)
