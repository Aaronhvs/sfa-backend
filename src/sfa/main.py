import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from sfa.api.v1.admin import router as admin_router
from sfa.api.v1.compare import router as compare_router
from sfa.api.v1.competitions import router as competitions_router
from sfa.api.v1.health import router as health_router
from sfa.api.v1.players import router as players_router
from sfa.api.v1.ranking import router as ranking_router
from sfa.api.v1.status import router as status_router
from sfa.core.config import get_settings
from sfa.infrastructure.database import AsyncSessionLocal, engine
from sfa.infrastructure.models import Base  # noqa: F401 — also registers all SQLAlchemy models
from sfa.infrastructure.redis_client import get_redis_client

logger = logging.getLogger(__name__)

settings = get_settings()

tags_metadata = [
    {"name": "ranking", "description": "Rankings de jugadores por temporada"},
    {"name": "players", "description": "Detalle de jugadores, eventos y fixtures"},
    {"name": "competitions", "description": "Competiciones y clasificaciones"},
    {"name": "compare", "description": "Comparación head-to-head entre dos jugadores"},
    {"name": "status", "description": "Estado del sistema"},
    {"name": "health", "description": "Health check de infraestructura"},
    {"name": "admin", "description": "Administración: disparar ingestas manualmente"},
]


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema: OK")

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


app = FastAPI(
    title="SFA — Stadistic Football Award API",
    description="API REST para consultar rankings, jugadores, eventos y competiciones del sistema SFA.",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(ranking_router, prefix="/api/v1", tags=["ranking"])
app.include_router(players_router, prefix="/api/v1", tags=["players"])
app.include_router(competitions_router, prefix="/api/v1", tags=["competitions"])
app.include_router(compare_router, prefix="/api/v1", tags=["compare"])
app.include_router(status_router, prefix="/api/v1", tags=["status"])
app.include_router(admin_router, prefix="/api/v1", tags=["admin"])
