from celery import Celery

from sfa.core.config import get_settings

settings = get_settings()

celery_app = Celery("sfa", broker=settings.CELERY_BROKER_URL)
