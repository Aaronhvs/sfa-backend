from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.application.use_cases.get_player_detail import (
    GetPlayerDetailUseCaseProtocol,
    PlayerDetailResult,
)


@dataclass(frozen=True)
class CompareResult:
    season: str
    player_a: PlayerDetailResult
    player_b: PlayerDetailResult


@runtime_checkable
class ComparePlayersUseCaseProtocol(Protocol):
    async def execute(
        self,
        player_a_id: int,
        player_b_id: int,
        season: str | None = None,
    ) -> CompareResult: ...


class ComparePlayersUseCase(ComparePlayersUseCaseProtocol):
    """Compara dos jugadores reutilizando GetPlayerDetailUseCase internamente."""

    def __init__(self, score_repo) -> None:
        from sfa.application.use_cases.get_player_detail import GetPlayerDetailUseCase
        self._detail_uc = GetPlayerDetailUseCase(score_repo)

    async def execute(
        self,
        player_a_id: int,
        player_b_id: int,
        season: str | None = None,
    ) -> CompareResult:
        detail_a = await self._detail_uc.execute(player_a_id, season)
        detail_b = await self._detail_uc.execute(player_b_id, season)

        resolved_season = detail_a.season or detail_b.season
        return CompareResult(
            season=resolved_season,
            player_a=detail_a,
            player_b=detail_b,
        )
