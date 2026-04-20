from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ingestion_ports import IngestionRepositoryPort
from sfa.infrastructure.models.competitions.models import Competition, CompetitionStage
from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.fixtures.models import Fixture
from sfa.infrastructure.models.ingestion.models import IngestionLog
from sfa.infrastructure.models.player_stats.models import PlayerStats
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore
from sfa.infrastructure.models.standings.models import StandingSnapshot
from sfa.infrastructure.models.teams.models import Team


class IngestionRepository(IngestionRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_competition(self, name: str, country: str, factor: float) -> int:
        stmt = (
            pg_insert(Competition)
            .values(name=name, country=country, competition_factor=factor)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"country": country, "competition_factor": factor},
            )
            .returning(Competition.id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    async def upsert_team(self, external_id: int, name: str, competition_id: int) -> int:
        # First try to link external_id to an already-seeded team by (name, competition_id)
        upd = (
            update(Team)
            .where(Team.name == name, Team.competition_id == competition_id, Team.external_id.is_(None))
            .values(external_id=external_id)
            .returning(Team.id)
        )
        result = await self._session.execute(upd)
        row = result.fetchone()
        if row:
            await self._session.flush()
            return row[0]

        # Otherwise upsert by external_id
        stmt = (
            pg_insert(Team)
            .values(external_id=external_id, name=name, competition_id=competition_id)
            .on_conflict_do_update(
                index_elements=["external_id"],
                set_={"name": name, "competition_id": competition_id},
            )
            .returning(Team.id)
        )
        result2 = await self._session.execute(stmt)
        await self._session.flush()
        return result2.scalar_one()

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
    ) -> int:
        stmt = (
            pg_insert(Player)
            .values(external_id=external_id, name=name, team_id=team_id, position=position)
            .on_conflict_do_update(
                index_elements=["external_id"],
                set_={"name": name, "team_id": team_id, "position": position},
            )
            .returning(Player.id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    async def upsert_fixture(
        self,
        external_id: int,
        competition_id: int,
        home_team_id: int,
        away_team_id: int,
        stage: str,
        season: str,
        played_at: object,
        matchday: int | None,
    ) -> int:
        stmt = (
            pg_insert(Fixture)
            .values(
                external_id=external_id,
                competition_id=competition_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                stage=stage,
                season=season,
                played_at=played_at,
                matchday=matchday,
            )
            .on_conflict_do_update(
                index_elements=["external_id"],
                set_={"stage": stage, "matchday": matchday},
            )
            .returning(Fixture.id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    async def upsert_standing_snapshot(
        self,
        competition_id: int,
        team_id: int,
        season: str,
        matchday: int,
        position: int,
        points: int,
    ) -> None:
        stmt = (
            pg_insert(StandingSnapshot)
            .values(
                competition_id=competition_id,
                team_id=team_id,
                season=season,
                matchday=matchday,
                position=position,
                points=points,
            )
            .on_conflict_do_update(
                constraint="uq_standing_snapshot",
                set_={"position": position, "points": points},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def upsert_player_event(
        self,
        player_id: int,
        fixture_id: int,
        minute: int,
        event_type: EventType,
        score_before: str | None,
        score_diff: int | None,
        psxg: float | None,
        m1: float,
        m2: float,
        m3: float,
        m4: float,
        mvisit: float,
        pts: float,
    ) -> None:
        stmt = pg_insert(PlayerEvent).values(
            player_id=player_id,
            fixture_id=fixture_id,
            minute=minute,
            event_type=event_type,
            score_before=score_before,
            score_diff=score_diff,
            psxg=psxg,
            m1=m1,
            m2=m2,
            m3=m3,
            m4=m4,
            mvisit=mvisit,
            pts=pts,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def upsert_player_stats(
        self, player_id: int, fixture_id: int, season: str, stats: dict,
    ) -> None:
        stmt = (
            pg_insert(PlayerStats)
            .values(
                player_id=player_id,
                fixture_id=fixture_id,
                season=season,
                goals=stats.get("goals", 0),
                assists=stats.get("assists", 0),
                corner_assists=stats.get("corner_assists", 0),
                shots_on=stats.get("shots_on", 0),
                xg=stats.get("xg", 0.0),
                xa=stats.get("xa", 0.0),
                passes_key=stats.get("passes_key", 0),
                progressive_passes=stats.get("progressive_passes", 0),
                progressive_carries=stats.get("progressive_carries", 0),
                recoveries_opp_half=stats.get("recoveries_opp_half", 0),
                pressures_success=stats.get("pressures_success", 0),
                duels_won=stats.get("duels_won", 0),
                dribbles_won=stats.get("dribbles_won", 0),
                tackles_won=stats.get("tackles_won", 0),
                interceptions=stats.get("interceptions", 0),
                blocks=stats.get("blocks", 0),
                clearances_goal_line=stats.get("clearances_goal_line", 0),
                minutes=stats.get("minutes", 0),
                appearances=stats.get("appearances", 1),
            )
            .on_conflict_do_update(
                constraint="uq_player_stats",
                set_={
                    "goals": stats.get("goals", 0),
                    "assists": stats.get("assists", 0),
                    "corner_assists": stats.get("corner_assists", 0),
                    "shots_on": stats.get("shots_on", 0),
                    "xg": stats.get("xg", 0.0),
                    "xa": stats.get("xa", 0.0),
                    "passes_key": stats.get("passes_key", 0),
                    "progressive_passes": stats.get("progressive_passes", 0),
                    "progressive_carries": stats.get("progressive_carries", 0),
                    "recoveries_opp_half": stats.get("recoveries_opp_half", 0),
                    "pressures_success": stats.get("pressures_success", 0),
                    "duels_won": stats.get("duels_won", 0),
                    "dribbles_won": stats.get("dribbles_won", 0),
                    "tackles_won": stats.get("tackles_won", 0),
                    "interceptions": stats.get("interceptions", 0),
                    "blocks": stats.get("blocks", 0),
                    "clearances_goal_line": stats.get("clearances_goal_line", 0),
                    "minutes": stats.get("minutes", 0),
                    "appearances": stats.get("appearances", 1),
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def upsert_season_score(
        self,
        player_id: int,
        competition_id: int,
        season: str,
        total_pts: float,
        matches_played: int,
        breakdown: dict,
    ) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(SFASeasonScore)
            .values(
                player_id=player_id,
                competition_id=competition_id,
                season=season,
                total_pts=total_pts,
                matches_played=matches_played,
                breakdown=breakdown,
                last_updated=now,
            )
            .on_conflict_do_update(
                constraint="uq_sfa_season_score",
                set_={
                    "total_pts": total_pts,
                    "matches_played": matches_played,
                    "breakdown": breakdown,
                    "last_updated": now,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_stage_factor(self, competition_id: int, stage: str) -> float:
        result = await self._session.execute(
            select(CompetitionStage.stage_factor).where(
                CompetitionStage.competition_id == competition_id,
                CompetitionStage.stage == stage,
            )
        )
        row = result.scalar_one_or_none()
        return float(row) if row is not None else 1.0

    async def save_ingestion_log(
        self,
        competition_id: int,
        season: str,
        status: IngestionStatus,
        players_processed: int | None,
        error_msg: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            pg_insert(IngestionLog).values(
                competition_id=competition_id,
                season=season,
                started_at=now,
                finished_at=now,
                status=status,
                players_processed=players_processed,
                error_msg=error_msg,
            )
        )
        await self._session.flush()

    async def delete_player_events_for_fixture(
        self, player_id: int, fixture_id: int,
    ) -> None:
        await self._session.execute(
            delete(PlayerEvent).where(
                PlayerEvent.player_id == player_id,
                PlayerEvent.fixture_id == fixture_id,
            )
        )
        await self._session.flush()
