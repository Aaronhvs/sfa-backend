from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import StandingEntryDTO, StandingRepositoryProtocol
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.standings.models import StandingSnapshot
from sfa.infrastructure.models.teams.models import Team


class StandingRepository(StandingRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_standings(
        self,
        competition_id: int,
        season: str | None = None,
        matchday: int | None = None,
    ) -> tuple[str, str, int, list[StandingEntryDTO]]:
        comp_result = await self._session.execute(
            select(Competition.name).where(Competition.id == competition_id)
        )
        competition_name = comp_result.scalar_one_or_none()
        if competition_name is None:
            raise ValueError("Competition not found")

        if season is None:
            result = await self._session.execute(
                select(func.max(StandingSnapshot.season)).where(
                    StandingSnapshot.competition_id == competition_id
                )
            )
            season = result.scalar_one_or_none()
            if season is None:
                raise ValueError("No standings found for this competition")

        if matchday is None:
            result = await self._session.execute(
                select(func.max(StandingSnapshot.matchday)).where(
                    StandingSnapshot.competition_id == competition_id,
                    StandingSnapshot.season == season,
                )
            )
            matchday = result.scalar_one_or_none()
            if matchday is None:
                raise ValueError("No standings found for the given season")

        stmt = (
            select(
                StandingSnapshot.position,
                Team.name.label("team"),
                StandingSnapshot.points,
            )
            .join(Team, StandingSnapshot.team_id == Team.id)
            .where(
                StandingSnapshot.competition_id == competition_id,
                StandingSnapshot.season == season,
                StandingSnapshot.matchday == matchday,
            )
            .order_by(StandingSnapshot.position)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        if not rows:
            raise ValueError("No standings found for the given season and matchday")

        entries = [StandingEntryDTO(**dict(row)) for row in rows]
        return (competition_name, season, matchday, entries)
