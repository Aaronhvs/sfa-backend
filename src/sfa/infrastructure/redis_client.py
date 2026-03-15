from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from sfa.core.config import get_settings

settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis_client()
    yield client
