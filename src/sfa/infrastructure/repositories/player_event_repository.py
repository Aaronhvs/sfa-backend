from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import (
    PlayerEventDTO,
    PlayerEventRepositoryProtocol,
    PlayerFixtureDTO,
)
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.fixtures.models import Fixture
from sfa.infrastructure.models.teams.models import Team


class PlayerEventRepository(PlayerEventRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_events_by_player(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerEventDTO]:
        home_alias = Team.__table__.alias("ht")
        away_alias = Team.__table__.alias("at")

        stmt = (
            select(
                PlayerEvent.id,
                Competition.name.label("competition"),
                Fixture.stage,
                Fixture.id.label("fixture_id"),
                home_alias.c.name.label("home_team"),
                away_alias.c.name.label("away_team"),
                Fixture.played_at,
                PlayerEvent.minute,
                PlayerEvent.event_type,
                PlayerEvent.score_before,
                PlayerEvent.score_diff,
                PlayerEvent.m1,
                PlayerEvent.m2,
                PlayerEvent.m3,
                PlayerEvent.m4,
                PlayerEvent.mvisit,
                PlayerEvent.pts,
            )
            .join(Fixture, PlayerEvent.fixture_id == Fixture.id)
            .join(Competition, Fixture.competition_id == Competition.id)
            .join(home_alias, Fixture.home_team_id == home_alias.c.id)
            .join(away_alias, Fixture.away_team_id == away_alias.c.id)
            .where(PlayerEvent.player_id == player_id)
            .order_by(Fixture.played_at.desc(), PlayerEvent.minute.asc())
        )
        if season is not None:
            stmt = stmt.where(Fixture.season == season)
        if competition_id is not None:
            stmt = stmt.where(Fixture.competition_id == competition_id)

        rows = (await self._session.execute(stmt)).mappings().all()
        return [PlayerEventDTO(**dict(row)) for row in rows]

    async def get_fixtures_by_player(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerFixtureDTO]:
        home_alias = Team.__table__.alias("ht")
        away_alias = Team.__table__.alias("at")

        stmt = (
            select(
                Fixture.id.label("fixture_id"),
                Competition.name.label("competition"),
                Fixture.stage,
                home_alias.c.name.label("home_team"),
                away_alias.c.name.label("away_team"),
                Fixture.played_at,
                func.sum(PlayerEvent.pts).label("sfa_pts"),
                func.count(PlayerEvent.id).label("events_count"),
            )
            .join(Fixture, PlayerEvent.fixture_id == Fixture.id)
            .join(Competition, Fixture.competition_id == Competition.id)
            .join(home_alias, Fixture.home_team_id == home_alias.c.id)
            .join(away_alias, Fixture.away_team_id == away_alias.c.id)
            .where(PlayerEvent.player_id == player_id)
            .group_by(
                Fixture.id,
                Competition.name,
                Fixture.stage,
                home_alias.c.name,
                away_alias.c.name,
                Fixture.played_at,
            )
            .order_by(Fixture.played_at.desc())
        )
        if season is not None:
            stmt = stmt.where(Fixture.season == season)
        if competition_id is not None:
            stmt = stmt.where(Fixture.competition_id == competition_id)

        rows = (await self._session.execute(stmt)).mappings().all()
        return [PlayerFixtureDTO(**dict(row)) for row in rows]
