from __future__ import annotations

from typing import Protocol, runtime_checkable

from sfa.domain.ports import PlayerEventDTO, PlayerEventRepositoryProtocol


@runtime_checkable
class GetPlayerEventsUseCaseProtocol(Protocol):
    async def execute(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerEventDTO]: ...


class GetPlayerEventsUseCase(GetPlayerEventsUseCaseProtocol):
    def __init__(self, event_repo: PlayerEventRepositoryProtocol) -> None:
        self._event_repo = event_repo

    async def execute(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerEventDTO]:
        return await self._event_repo.get_events_by_player(
            player_id, season, competition_id,
        )
