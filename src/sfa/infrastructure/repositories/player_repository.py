from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import PlayerDTO, PlayerRepositoryProtocol
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.teams.models import Team


class PlayerRepository(PlayerRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, player_id: int) -> PlayerDTO | None:
        stmt = (
            select(Player.id, Player.name, Player.position, Player.photo_url, Team.name.label("team_name"))
            .join(Team, Player.team_id == Team.id)
            .where(Player.id == player_id)
        )
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None
        return PlayerDTO(
            id=row["id"],
            name=row["name"],
            position=row["position"].value,
            photo_url=row["photo_url"],
            team_name=row["team_name"],
        )

    async def exists(self, player_id: int) -> bool:
        stmt = select(Player.id).where(Player.id == player_id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None
