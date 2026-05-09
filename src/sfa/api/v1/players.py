from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from sfa.api.v1.schemas.players import (
    BreakdownEntrySchema,
    PlayerDetailSchema,
    PlayerEventSchema,
    PlayerFixtureSchema,
)
from sfa.application.use_cases.get_player_detail import (
    GetPlayerDetailUseCase,
    PlayerNotFoundError,
)
from sfa.application.use_cases.get_player_events import GetPlayerEventsUseCase
from sfa.application.use_cases.get_player_fixtures import GetPlayerFixturesUseCase
from sfa.core.dependencies import (
    get_player_detail_use_case,
    get_player_events_use_case,
    get_player_fixtures_use_case,
)

router = APIRouter()


@router.get("/players/{player_id}", response_model=PlayerDetailSchema)
async def get_player(
    player_id: int,
    use_case: Annotated[GetPlayerDetailUseCase, Depends(get_player_detail_use_case)],
    season: str | None = Query(default=None),
):
    try:
        result = await use_case.execute(player_id, season)
    except PlayerNotFoundError:
        raise HTTPException(status_code=404, detail="Player not found")

    return PlayerDetailSchema(
        id=result.id,
        name=result.name,
        team=result.team,
        position=result.position,
        competition=result.competition,
        sfa_pts=result.sfa_pts,
        matches=result.matches,
        photo_url=result.photo_url,
        global_rank=result.global_rank,
        season=result.season,
        breakdown={
            k: BreakdownEntrySchema(count=v.count, pts=v.pts)
            for k, v in result.breakdown.items()
        } if result.breakdown else None,
        competitions=result.competitions,
    )


@router.get("/players/{player_id}/events", response_model=list[PlayerEventSchema])
async def get_player_events(
    player_id: int,
    use_case: Annotated[GetPlayerEventsUseCase, Depends(get_player_events_use_case)],
    season: str | None = Query(default=None),
    competition_id: int | None = Query(default=None),
):
    events = await use_case.execute(player_id, season, competition_id)
    return [PlayerEventSchema(**e.__dict__) for e in events]


@router.get("/players/{player_id}/fixtures", response_model=list[PlayerFixtureSchema])
async def get_player_fixtures(
    player_id: int,
    use_case: Annotated[GetPlayerFixturesUseCase, Depends(get_player_fixtures_use_case)],
    season: str | None = Query(default=None),
    competition_id: int | None = Query(default=None),
):
    fixtures = await use_case.execute(player_id, season, competition_id)
    return [PlayerFixtureSchema(**f.__dict__) for f in fixtures]
