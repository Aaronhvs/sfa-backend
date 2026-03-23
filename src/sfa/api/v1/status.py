from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.api.v1.schemas.status import StatusResponseSchema
from sfa.core.config import get_settings
from sfa.core.dependencies import get_db
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore

router = APIRouter()


@router.get("/status", response_model=StatusResponseSchema)
async def get_status(db: Annotated[AsyncSession, Depends(get_db)]):
    settings = get_settings()

    players_count, scores_count, competitions_count, events_count = (
        await db.scalar(select(func.count()).select_from(Player)),
        await db.scalar(select(func.count()).select_from(SFASeasonScore)),
        await db.scalar(select(func.count()).select_from(Competition)),
        await db.scalar(select(func.count()).select_from(PlayerEvent)),
    )

    latest_season = await db.scalar(select(func.max(SFASeasonScore.season)))

    return StatusResponseSchema(
        status="ok",
        season=latest_season,
        players=players_count or 0,
        scores=scores_count or 0,
        competitions=competitions_count or 0,
        events=events_count or 0,
        api_version=settings.APP_VERSION,
    )
