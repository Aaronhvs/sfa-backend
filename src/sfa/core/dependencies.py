from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.infrastructure.database import get_db
from sfa.infrastructure.redis_client import get_redis
from sfa.infrastructure.repositories import (
    CompetitionRepository,
    IngestionRepository,
    PlayerEventRepository,
    PlayerRepository,
    RawDataRepository,
    SFAScoreRepository,
    StandingRepository,
    SystemRepository,
)

# ─── Repositorios ────────────────────────────────────────────────────



async def get_player_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlayerRepository:
    return PlayerRepository(db)


async def get_sfa_score_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SFAScoreRepository:
    return SFAScoreRepository(db)


async def get_competition_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompetitionRepository:
    return CompetitionRepository(db)


async def get_standing_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StandingRepository:
    return StandingRepository(db)


async def get_player_event_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlayerEventRepository:
    return PlayerEventRepository(db)


async def get_system_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemRepository:
    return SystemRepository(db)


async def get_ingestion_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IngestionRepository:
    return IngestionRepository(db)


async def get_raw_data_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RawDataRepository:
    return RawDataRepository(db)


# ─── Use Cases ───────────────────────────────────────────────────────

from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
from sfa.application.use_cases.compare_players import ComparePlayersUseCase
from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
from sfa.application.use_cases.get_player_detail import GetPlayerDetailUseCase
from sfa.application.use_cases.get_player_events import GetPlayerEventsUseCase
from sfa.application.use_cases.get_player_fixtures import GetPlayerFixturesUseCase
from sfa.application.use_cases.get_ranking import GetRankingUseCase
from sfa.application.use_cases.get_standings import GetStandingsUseCase
from sfa.application.use_cases.get_status import GetStatusUseCase
from sfa.application.use_cases.list_competitions import ListCompetitionsUseCase
from sfa.core.config import get_settings
from sfa.domain.scoring.services import SFAScoringService
from sfa.infrastructure.providers.api_football import APIFootballProvider


async def get_player_detail_use_case(
    score_repo: Annotated[SFAScoreRepository, Depends(get_sfa_score_repository)],
) -> GetPlayerDetailUseCase:
    return GetPlayerDetailUseCase(score_repo)


async def get_ranking_use_case(
    score_repo: Annotated[SFAScoreRepository, Depends(get_sfa_score_repository)],
) -> GetRankingUseCase:
    return GetRankingUseCase(score_repo)


async def get_player_events_use_case(
    event_repo: Annotated[PlayerEventRepository, Depends(get_player_event_repository)],
) -> GetPlayerEventsUseCase:
    return GetPlayerEventsUseCase(event_repo)


async def get_player_fixtures_use_case(
    event_repo: Annotated[PlayerEventRepository, Depends(get_player_event_repository)],
) -> GetPlayerFixturesUseCase:
    return GetPlayerFixturesUseCase(event_repo)


async def get_compare_players_use_case(
    score_repo: Annotated[SFAScoreRepository, Depends(get_sfa_score_repository)],
) -> ComparePlayersUseCase:
    return ComparePlayersUseCase(score_repo)


async def get_list_competitions_use_case(
    comp_repo: Annotated[CompetitionRepository, Depends(get_competition_repository)],
) -> ListCompetitionsUseCase:
    return ListCompetitionsUseCase(comp_repo)


async def get_standings_use_case(
    standing_repo: Annotated[StandingRepository, Depends(get_standing_repository)],
) -> GetStandingsUseCase:
    return GetStandingsUseCase(standing_repo)


async def get_status_use_case(
    system_repo: Annotated[SystemRepository, Depends(get_system_repository)],
) -> GetStatusUseCase:
    return GetStatusUseCase(system_repo)


def get_api_football_provider() -> APIFootballProvider:
    settings = get_settings()
    return APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)


def get_sfa_scoring_service() -> SFAScoringService:
    return SFAScoringService()


async def get_download_player_data_use_case(
    provider: Annotated[APIFootballProvider, Depends(get_api_football_provider)],
    repo: Annotated[IngestionRepository, Depends(get_ingestion_repository)],
) -> DownloadPlayerDataUseCase:
    return DownloadPlayerDataUseCase(provider, repo)


async def get_calculate_sfa_from_raw_use_case(
    raw_repo: Annotated[RawDataRepository, Depends(get_raw_data_repository)],
    ingestion_repo: Annotated[IngestionRepository, Depends(get_ingestion_repository)],
    scoring: Annotated[SFAScoringService, Depends(get_sfa_scoring_service)],
) -> CalculateSFAFromRawUseCase:
    return CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, scoring)


__all__ = ["get_db", "get_redis"]
