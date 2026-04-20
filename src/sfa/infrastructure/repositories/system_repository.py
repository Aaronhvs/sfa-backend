from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import SystemCountsDTO, SystemRepositoryProtocol
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore


class SystemRepository(SystemRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_counts(self) -> SystemCountsDTO:
        players = await self._session.scalar(select(func.count()).select_from(Player))
        scores = await self._session.scalar(select(func.count()).select_from(SFASeasonScore))
        competitions = await self._session.scalar(select(func.count()).select_from(Competition))
        events = await self._session.scalar(select(func.count()).select_from(PlayerEvent))
        latest_season = await self._session.scalar(select(func.max(SFASeasonScore.season)))

        return SystemCountsDTO(
            players=players or 0,
            scores=scores or 0,
            competitions=competitions or 0,
            events=events or 0,
            latest_season=latest_season,
        )
