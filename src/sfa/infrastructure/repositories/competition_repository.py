from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import CompetitionDTO, CompetitionRepositoryProtocol
from sfa.infrastructure.models.competitions.models import Competition


class CompetitionRepository(CompetitionRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> list[CompetitionDTO]:
        stmt = select(
            Competition.id,
            Competition.name,
            Competition.country,
            Competition.competition_factor.label("factor"),
        ).order_by(Competition.name)
        rows = (await self._session.execute(stmt)).mappings().all()
        return [CompetitionDTO(**dict(row)) for row in rows]

    async def get_by_id(self, competition_id: int) -> CompetitionDTO | None:
        stmt = select(
            Competition.id,
            Competition.name,
            Competition.country,
            Competition.competition_factor.label("factor"),
        ).where(Competition.id == competition_id)
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None
        return CompetitionDTO(**dict(row))
