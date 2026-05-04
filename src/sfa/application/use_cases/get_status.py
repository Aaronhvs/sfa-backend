from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.domain.ports import SystemRepositoryProtocol


@dataclass(frozen=True)
class StatusResult:
    players: int
    scores: int
    competitions: int
    events: int
    latest_season: str | None


@runtime_checkable
class GetStatusUseCaseProtocol(Protocol):
    async def execute(self) -> StatusResult: ...


class GetStatusUseCase(GetStatusUseCaseProtocol):
    def __init__(self, system_repo: SystemRepositoryProtocol) -> None:
        self._system_repo = system_repo

    async def execute(self) -> StatusResult:
        counts = await self._system_repo.get_counts()
        return StatusResult(
            players=counts.players,
            scores=counts.scores,
            competitions=counts.competitions,
            events=counts.events,
            latest_season=counts.latest_season,
        )
