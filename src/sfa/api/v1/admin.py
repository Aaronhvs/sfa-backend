from fastapi import APIRouter, Query

from sfa.tasks.enrichment_tasks import (
    enrich_all_task,
    enrich_fbref_task,
    enrich_understat_task,
    recalculate_task,
)
from sfa.tasks.ingestion_tasks import (
    ingest_all_competitions_task,
    ingest_competition_task,
    recalculate_sfa_task,
)

router = APIRouter(prefix="/admin", tags=["admin"])

CURRENT_SEASON = 2024
CURRENT_SEASON_STR = "2024"


@router.post("/ingest/{league_id}")
async def trigger_ingest_competition(
    league_id: int,
    season: int = Query(default=CURRENT_SEASON),
):
    """Trigger ingestion of a specific league as an async Celery task."""
    task = ingest_competition_task.delay(league_id, season)
    return {"task_id": task.id, "league_id": league_id, "season": season}


@router.post("/ingest-all")
async def trigger_ingest_all(
    season: int = Query(default=CURRENT_SEASON),
):
    """Trigger ingestion of all configured leagues as an async Celery task."""
    task = ingest_all_competitions_task.delay(season)
    return {"task_id": task.id, "season": season}


@router.get("/ingestion-logs")
async def get_ingestion_logs():
    """Return recent ingestion logs."""
    # TODO: inject repo and query IngestionLog
    return {"logs": []}


@router.post("/enrich-fbref/{competition_id}")
async def trigger_enrich_fbref(
    competition_id: int,
    competition_name: str = Query(...),
    season: str = Query(default=CURRENT_SEASON_STR),
):
    """Trigger FBref enrichment + score recalculation for one league."""
    task = enrich_fbref_task.delay(competition_name, competition_id, season)
    return {"task_id": task.id, "competition_id": competition_id}


@router.post("/enrich-understat/{competition_id}")
async def trigger_enrich_understat(
    competition_id: int,
    competition_name: str = Query(...),
    season: str = Query(default=CURRENT_SEASON_STR),
    season_int: int = Query(default=CURRENT_SEASON),
):
    """Trigger Understat enrichment + score recalculation for one league."""
    task = enrich_understat_task.delay(
        competition_name, competition_id, season, season_int
    )
    return {"task_id": task.id, "competition_id": competition_id}


@router.post("/enrich-all")
async def trigger_enrich_all(
    season: str = Query(default=CURRENT_SEASON_STR),
    season_int: int = Query(default=CURRENT_SEASON),
):
    """Trigger full enrichment pipeline for all leagues."""
    task = enrich_all_task.delay(season, season_int)
    return {"task_id": task.id, "season": season}


@router.post("/recalculate/{competition_id}")
async def trigger_recalculate(
    competition_id: int,
    season: str = Query(default=CURRENT_SEASON_STR),
):
    """Recalculate SFA scores for a league (useful after parameter changes)."""
    task = recalculate_task.delay(competition_id, season)
    return {"task_id": task.id, "competition_id": competition_id}


@router.post("/recalculate")
async def trigger_recalculate_sfa(
    competition_id: int = Query(...),
    season: str = Query(default=CURRENT_SEASON_STR),
):
    """Recalculate SFA scores from RAW data without any API calls."""
    task = recalculate_sfa_task.delay(competition_id, season)
    return {"task_id": task.id, "competition_id": competition_id, "season": season}
