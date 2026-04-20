from celery import Celery
from celery.schedules import crontab

from sfa.core.config import get_settings

settings = get_settings()

celery_app = Celery("sfa", broker=settings.CELERY_BROKER_URL)

celery_app.autodiscover_tasks(["sfa.tasks"])

celery_app.conf.beat_schedule = {
    "ingest-all-competitions-every-8h": {
        "task": "sfa.tasks.ingestion_tasks.ingest_all_competitions_task",
        "schedule": crontab(hour="*/8"),
        "args": (2024,),
    },
}

celery_app.conf.timezone = "UTC"
