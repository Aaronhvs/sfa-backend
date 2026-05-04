from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.domain.ports import SFAScoreRepositoryProtocol


@dataclass(frozen=True)
class BreakdownEntry:
    count: int
    pts: float


@dataclass(frozen=True)
class PlayerDetailResult:
    id: int
    name: str
    team: str
    position: str
    competition: str
    sfa_pts: float
    matches: int
    photo_url: str | None
    global_rank: int
    season: str
    breakdown: dict[str, BreakdownEntry] | None
    competitions: list[str]


@runtime_checkable
class GetPlayerDetailUseCaseProtocol(Protocol):
    async def execute(
        self, player_id: int, season: str | None = None,
    ) -> PlayerDetailResult: ...


class GetPlayerDetailUseCase(GetPlayerDetailUseCaseProtocol):
    """Orquesta la obtención del detalle de un jugador.

    Lógica movida desde players.py _get_player_detail.
    """

    def __init__(self, score_repo: SFAScoreRepositoryProtocol) -> None:
        self._score_repo = score_repo

    async def execute(
        self, player_id: int, season: str | None = None,
    ) -> PlayerDetailResult:
        # 1. Resolver season
        if season is None:
            season = await self._score_repo.latest_season_for_player(player_id)

        if season is None:
            raise PlayerNotFoundError(player_id)

        # 2. Obtener score principal
        score = await self._score_repo.get_best_score_for_player_season(player_id, season)
        if score is None:
            raise PlayerNotFoundError(player_id)

        # 3. Calcular rank global
        global_rank = await self._score_repo.get_global_rank(
            player_id, season, score.total_pts,
        )

        # 4. Obtener competitions
        competitions = await self._score_repo.get_competitions_for_player_season(
            player_id, season,
        )

        # 5. Parsear breakdown
        breakdown: dict[str, BreakdownEntry] | None = None
        if score.breakdown:
            breakdown = {
                k: BreakdownEntry(**v)
                for k, v in score.breakdown.items()
                if isinstance(v, dict) and "count" in v and "pts" in v
            }

        return PlayerDetailResult(
            id=score.player_id,
            name=score.player_name,
            team=score.team_name,
            position=score.position,
            competition=score.competition_name,
            sfa_pts=score.total_pts,
            matches=score.matches_played,
            photo_url=score.photo_url,
            global_rank=global_rank,
            season=season,
            breakdown=breakdown,
            competitions=competitions,
        )


class PlayerNotFoundError(Exception):
    def __init__(self, player_id: int) -> None:
        self.player_id = player_id
        super().__init__(f"Player {player_id} not found")
