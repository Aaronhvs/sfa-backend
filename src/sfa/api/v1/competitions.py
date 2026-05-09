from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from sfa.api.v1.schemas.competitions import (
    CompetitionSchema,
    StandingEntrySchema,
    StandingsResponseSchema,
)
from sfa.application.use_cases.get_standings import GetStandingsUseCase
from sfa.application.use_cases.list_competitions import ListCompetitionsUseCase
from sfa.core.dependencies import get_list_competitions_use_case, get_standings_use_case

router = APIRouter()


@router.get("/competitions", response_model=list[CompetitionSchema])
async def list_competitions(
    use_case: Annotated[ListCompetitionsUseCase, Depends(get_list_competitions_use_case)],
):
    comps = await use_case.execute()
    return [CompetitionSchema(**c.__dict__) for c in comps]


@router.get(
    "/competitions/{competition_id}/standings",
    response_model=StandingsResponseSchema,
)
async def get_standings(
    competition_id: int,
    use_case: Annotated[GetStandingsUseCase, Depends(get_standings_use_case)],
    season: str | None = Query(default=None),
    matchday: int | None = Query(default=None),
):
    try:
        result = await use_case.execute(competition_id, season, matchday)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return StandingsResponseSchema(
        competition=result.competition,
        season=result.season,
        matchday=result.matchday,
        standings=[StandingEntrySchema(**s.__dict__) for s in result.standings],
    )
