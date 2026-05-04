import asyncio

from sfa.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def enrich_fbref_task(self, competition_name: str, competition_id: int, season: str):
    """FBref enrichment for one league, then recalculate scores."""
    try:
        asyncio.run(_run_enrich_fbref(competition_name, competition_id, season))
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def enrich_understat_task(
    self,
    competition_name: str,
    competition_id: int,
    season: str,
    season_int: int,
):
    """Understat enrichment for one league (PSxG fallback), then recalculate."""
    try:
        asyncio.run(
            _run_enrich_understat(competition_name, competition_id, season, season_int)
        )
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def enrich_all_task(self, season: str, season_int: int):
    """Full sequential enrichment: for each league → FBref → Understat → Recalculate."""
    try:
        asyncio.run(_run_enrich_all(season, season_int))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def recalculate_task(self, competition_id: int, season: str):
    """Recalculate SFA scores for a league (useful after parameter changes)."""
    try:
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _run_enrich_fbref(
    competition_name: str, competition_id: int, season: str,
) -> None:
    from sfa.application.use_cases.enrich_with_fbref import EnrichWithFBrefUseCase
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.fbref_scraper import FBrefScraper
    from sfa.infrastructure.repositories.enrichment_repository import EnrichmentRepository

    scraper = FBrefScraper()
    async with AsyncSessionLocal() as session:
        repo = EnrichmentRepository(session)
        use_case = EnrichWithFBrefUseCase(scraper, repo)
        result = await use_case.execute(competition_name, competition_id, season)
        await session.commit()
    return result


async def _run_enrich_understat(
    competition_name: str, competition_id: int, season: str, season_int: int,
) -> None:
    from sfa.application.use_cases.enrich_with_understat import EnrichWithUnderstatUseCase
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.understat_scraper import UnderstatScraper
    from sfa.infrastructure.repositories.enrichment_repository import EnrichmentRepository

    scraper = UnderstatScraper()
    async with AsyncSessionLocal() as session:
        repo = EnrichmentRepository(session)
        use_case = EnrichWithUnderstatUseCase(scraper, repo)
        result = await use_case.execute(
            competition_name, competition_id, season, season_int
        )
        await session.commit()
    return result


async def _run_recalculate(competition_id: int, season: str) -> None:
    from sfa.application.use_cases.recalculate_scores import RecalculateScoresUseCase
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.repositories.enrichment_repository import EnrichmentRepository

    async with AsyncSessionLocal() as session:
        repo = EnrichmentRepository(session)
        use_case = RecalculateScoresUseCase(repo)
        result = await use_case.execute(competition_id, season)
        await session.commit()
    return result


async def _run_enrich_all(season: str, season_int: int) -> None:
    from sfa.application.use_cases.ingest_competition import LEAGUES

    for league in LEAGUES:
        # FBref
        await _run_enrich_fbref(league.name, league.id, season)
        # Understat (skips Champions League internally)
        await _run_enrich_understat(league.name, league.id, season, season_int)
        # Recalculate
        await _run_recalculate(league.id, season)
