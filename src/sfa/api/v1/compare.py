from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from sfa.api.v1.schemas.compare import CompareResponseSchema
from sfa.api.v1.schemas.players import BreakdownEntrySchema, PlayerDetailSchema
from sfa.application.use_cases.compare_players import ComparePlayersUseCase
from sfa.application.use_cases.get_player_detail import PlayerNotFoundError
from sfa.core.dependencies import get_compare_players_use_case

router = APIRouter()


def _detail_to_schema(r) -> PlayerDetailSchema:
    return PlayerDetailSchema(
        id=r.id,
        name=r.name,
        team=r.team,
        position=r.position,
        competition=r.competition,
        sfa_pts=r.sfa_pts,
        matches=r.matches,
        photo_url=r.photo_url,
        global_rank=r.global_rank,
        season=r.season,
        breakdown={
            k: BreakdownEntrySchema(count=v.count, pts=v.pts)
            for k, v in r.breakdown.items()
        } if r.breakdown else None,
        competitions=r.competitions,
    )


@router.get("/compare", response_model=CompareResponseSchema)
async def compare_players(
    use_case: Annotated[ComparePlayersUseCase, Depends(get_compare_players_use_case)],
    player_a: int = Query(..., description="ID del primer jugador"),
    player_b: int = Query(..., description="ID del segundo jugador"),
    season: str | None = Query(default=None),
):
    try:
        result = await use_case.execute(player_a, player_b, season)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found")

    return CompareResponseSchema(
        season=result.season,
        player_a=_detail_to_schema(result.player_a),
        player_b=_detail_to_schema(result.player_b),
    )
