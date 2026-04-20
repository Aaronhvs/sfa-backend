from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.domain.ports import RankedPlayerDTO, SFAScoreRepositoryProtocol


@dataclass(frozen=True)
class RankingResult:
    season: str
    total: int
    ranking: list[RankedPlayerDTO]


@runtime_checkable
class GetRankingUseCaseProtocol(Protocol):
    async def execute(
        self,
        season: str | None = None,
        position: str | None = None,
        competition_id: int | None = None,
        limit: int = 50,
    ) -> RankingResult: ...


class GetRankingUseCase(GetRankingUseCaseProtocol):
    def __init__(self, score_repo: SFAScoreRepositoryProtocol) -> None:
        self._score_repo = score_repo

    async def execute(
        self,
        season: str | None = None,
        position: str | None = None,
        competition_id: int | None = None,
        limit: int = 50,
    ) -> RankingResult:
        if season is None:
            season = await self._score_repo.latest_season()

        if season is None:
            return RankingResult(season="", total=0, ranking=[])

        ranking = await self._score_repo.get_ranking(
            season, position, competition_id, limit,
        )
        total = await self._score_repo.get_ranking_total(
            season, position, competition_id,
        )
        return RankingResult(season=season, total=total, ranking=ranking)
