from fastapi import APIRouter, Query

from sfa.tasks.ingestion_tasks import ingest_all_competitions_task, ingest_competition_task

router = APIRouter(prefix="/admin", tags=["admin"])

CURRENT_SEASON = 2024


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
