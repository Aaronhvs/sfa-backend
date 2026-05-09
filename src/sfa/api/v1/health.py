from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.core.config import get_settings
from sfa.core.dependencies import get_db, get_redis

router = APIRouter()


@router.get("/health")
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    settings = get_settings()

    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"

    try:
        await redis.ping()
        redis_status = "connected"
    except Exception:
        redis_status = "error"

    return {
        "status": "ok",
        "database": db_status,
        "redis": redis_status,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
    }
