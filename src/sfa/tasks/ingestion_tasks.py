import asyncio

from sfa.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_competition_task(self, league_id: int, season: int):
    """Download raw data + calculate SFA for a single league."""
    try:
        asyncio.run(_run_ingest_competition(league_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def ingest_all_competitions_task(self, season: int):
    """Download raw data + calculate SFA for all configured leagues."""
    try:
        asyncio.run(_run_ingest_all(season))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3)
def recalculate_sfa_task(self, competition_id: int, season: str):
    """Recalculate SFA scores from RAW data — no external API calls."""
    try:
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _run_ingest_competition(league_id: int, season: int):
    from sqlalchemy import select

    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
    from sfa.core.config import get_settings
    from sfa.domain.ingestion_ports import LEAGUES
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.models.competitions.models import Competition
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    league = next((l for l in LEAGUES if l.id == league_id), None)
    if league is None:
        raise ValueError(f"League not found: {league_id}")

    season_str = str(season)

    async with AsyncSessionLocal() as session:
        download_uc = DownloadPlayerDataUseCase(provider, IngestionRepository(session))
        download_result = await download_uc.execute(league, season)
        await session.commit()

    if download_result.status == "failed":
        return download_result

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Competition.id).where(Competition.name == league.name)
        )
        competition_id = row.scalar_one()

        calc_uc = CalculateSFAFromRawUseCase(
            RawDataRepository(session), IngestionRepository(session), scoring
        )
        calc_result = await calc_uc.execute(competition_id, season_str)
        await session.commit()

    return calc_result


async def _run_ingest_all(season: int):
    from sqlalchemy import select

    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
    from sfa.core.config import get_settings
    from sfa.domain.ingestion_ports import LEAGUES
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.models.competitions.models import Competition
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()
    season_str = str(season)
    results = []

    for league in LEAGUES:
        if provider.requests_used >= 7000:
            break

        async with AsyncSessionLocal() as session:
            download_uc = DownloadPlayerDataUseCase(provider, IngestionRepository(session))
            download_result = await download_uc.execute(league, season)
            await session.commit()

        if download_result.status == "failed":
            results.append(download_result)
            continue

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(Competition.id).where(Competition.name == league.name)
            )
            competition_id = row.scalar_one()

            calc_uc = CalculateSFAFromRawUseCase(
                RawDataRepository(session), IngestionRepository(session), scoring
            )
            calc_result = await calc_uc.execute(competition_id, season_str)
            await session.commit()

        results.append(calc_result)

    return results


async def _run_recalculate(competition_id: int, season: str):
    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    scoring = SFAScoringService()

    async with AsyncSessionLocal() as session:
        calc_uc = CalculateSFAFromRawUseCase(
            RawDataRepository(session), IngestionRepository(session), scoring
        )
        result = await calc_uc.execute(competition_id, season)
        await session.commit()

    return result
