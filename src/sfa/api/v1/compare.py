from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.api.v1.players import _get_player_detail
from sfa.api.v1.schemas.compare import CompareResponseSchema
from sfa.core.dependencies import get_db

router = APIRouter()


@router.get("/compare", response_model=CompareResponseSchema)
async def compare_players(
    db: Annotated[AsyncSession, Depends(get_db)],
    player_a: int = Query(..., description="ID del primer jugador"),
    player_b: int = Query(..., description="ID del segundo jugador"),
    season: str | None = Query(default=None),
):
    detail_a = await _get_player_detail(player_a, db, season)
    detail_b = await _get_player_detail(player_b, db, season)

    resolved_season = detail_a.season or detail_b.season
    return CompareResponseSchema(
        season=resolved_season,
        player_a=detail_a,
        player_b=detail_b,
    )
