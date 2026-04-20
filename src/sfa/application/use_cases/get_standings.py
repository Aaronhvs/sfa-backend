from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.domain.ports import StandingEntryDTO, StandingRepositoryProtocol


@dataclass(frozen=True)
class StandingsResult:
    competition: str
    season: str
    matchday: int
    standings: list[StandingEntryDTO]


@runtime_checkable
class GetStandingsUseCaseProtocol(Protocol):
    async def execute(
        self,
        competition_id: int,
        season: str | None = None,
        matchday: int | None = None,
    ) -> StandingsResult: ...


class GetStandingsUseCase(GetStandingsUseCaseProtocol):
    def __init__(self, standing_repo: StandingRepositoryProtocol) -> None:
        self._standing_repo = standing_repo

    async def execute(
        self,
        competition_id: int,
        season: str | None = None,
        matchday: int | None = None,
    ) -> StandingsResult:
        comp_name, season_resolved, matchday_resolved, entries = (
            await self._standing_repo.get_standings(competition_id, season, matchday)
        )
        return StandingsResult(
            competition=comp_name,
            season=season_resolved,
            matchday=matchday_resolved,
            standings=entries,
        )
