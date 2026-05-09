from typing import Annotated

from fastapi import APIRouter, Depends

from sfa.api.v1.schemas.status import StatusResponseSchema
from sfa.application.use_cases.get_status import GetStatusUseCase
from sfa.core.config import get_settings
from sfa.core.dependencies import get_status_use_case

router = APIRouter()


@router.get("/status", response_model=StatusResponseSchema)
async def get_status(
    use_case: Annotated[GetStatusUseCase, Depends(get_status_use_case)],
):
    settings = get_settings()
    result = await use_case.execute()
    return StatusResponseSchema(
        status="ok",
        season=result.latest_season,
        players=result.players,
        scores=result.scores,
        competitions=result.competitions,
        events=result.events,
        api_version=settings.APP_VERSION,
    )
