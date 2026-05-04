from typing import Annotated

from fastapi import APIRouter, Depends, Query

from sfa.api.v1.schemas.ranking import RankedPlayerSchema, RankingResponseSchema
from sfa.application.use_cases.get_ranking import GetRankingUseCase
from sfa.core.dependencies import get_ranking_use_case

router = APIRouter()


@router.get("/ranking", response_model=RankingResponseSchema)
async def get_ranking(
    use_case: Annotated[GetRankingUseCase, Depends(get_ranking_use_case)],
    season: str | None = Query(default=None, description="Temporada, ej: 2024-25"),
    position: str | None = Query(default=None, description="Posición: DEL, EXT, MC, DC, LAT, GK"),
    competition_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    result = await use_case.execute(season, position, competition_id, limit)
    return RankingResponseSchema(
        season=result.season,
        total=result.total,
        ranking=[
            RankedPlayerSchema(
                rank=r.rank,
                id=r.player_id,
                name=r.player_name,
                team=r.team_name,
                position=r.position,
                competition=r.competition_name,
                sfa_pts=r.total_pts,
                matches=r.matches_played,
                photo_url=r.photo_url,
            )
            for r in result.ranking
        ],
    )
