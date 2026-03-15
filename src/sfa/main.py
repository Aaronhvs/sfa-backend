import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from sfa.api.v1.health import router as health_router
from sfa.core.config import get_settings
from sfa.infrastructure.database import AsyncSessionLocal
from sfa.infrastructure.redis_client import get_redis_client

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)

    try:
        redis = get_redis_client()
        await redis.ping()
        logger.info("Redis connection: OK")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)

    yield


app = FastAPI(title="SFA API", version=settings.APP_VERSION, lifespan=lifespan)

app.include_router(health_router, prefix="/api/v1")
