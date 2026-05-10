from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ingestion_ports import LeagueConfigDTO, LeagueConfigRepositoryPort
from sfa.infrastructure.models.competitions.models import Competition


class LeagueConfigRepository(LeagueConfigRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]:
        stmt = select(Competition).where(Competition.providers.has_key(provider_name))
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            LeagueConfigDTO(
                competition_id=row.id,
                external_id=int(row.providers[provider_name]),
                name=row.name,
                country=row.country,
                comp_factor=float(row.competition_factor),
                top_n=row.top_n,
            )
            for row in rows
        ]

    async def get_league_by_external_id(
        self, provider_name: str, external_id: int,
    ) -> LeagueConfigDTO | None:
        stmt = select(Competition).where(
            Competition.providers[provider_name].as_string() == str(external_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        return LeagueConfigDTO(
            competition_id=row.id,
            external_id=int(row.providers[provider_name]),
            name=row.name,
            country=row.country,
            comp_factor=float(row.competition_factor),
            top_n=row.top_n,
        )
