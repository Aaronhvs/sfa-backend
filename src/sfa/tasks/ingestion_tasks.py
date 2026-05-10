import asyncio

from sfa.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_competition_task(self, league_id: int, season: int):
    """Ingest a single league. Thin sync → async wrapper."""
    try:
        asyncio.run(_run_ingest_competition(league_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def ingest_all_competitions_task(self, season: int):
    """Ingest all configured leagues."""
    try:
        asyncio.run(_run_ingest_all(season))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _run_ingest_competition(league_id: int, season: int):
    from sfa.application.use_cases.ingest_competition import IngestCompetitionUseCase
    from sfa.core.config import get_settings
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.league_config_repository import LeagueConfigRepository

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    async with AsyncSessionLocal() as session:
        league_config_repo = LeagueConfigRepository(session)
        league = await league_config_repo.get_league_by_external_id("api-football", league_id)
        if league is None:
            raise ValueError(f"League not found: {league_id}")

        repo = IngestionRepository(session)
        use_case = IngestCompetitionUseCase(provider, repo, scoring)
        result = await use_case.execute(league, season)
        await session.commit()

    return result


async def _run_ingest_all(season: int):
    from sfa.application.use_cases.ingest_all import IngestAllCompetitionsUseCase
    from sfa.core.config import get_settings
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.league_config_repository import LeagueConfigRepository

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    async with AsyncSessionLocal() as session:
        repo = IngestionRepository(session)
        league_config_repo = LeagueConfigRepository(session)
        use_case = IngestAllCompetitionsUseCase(provider, repo, scoring, league_config_repo)
        results = await use_case.execute(season)
        await session.commit()

    return results
