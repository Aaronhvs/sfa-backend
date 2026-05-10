from __future__ import annotations

from sfa.application.use_cases.ingest_competition import IngestCompetitionUseCase, IngestionResult
from sfa.domain.ingestion_ports import (
    FootballDataProviderPort,
    IngestionRepositoryPort,
    LeagueConfigRepositoryPort,
)
from sfa.domain.scoring.services import SFAScoringService


class IngestAllCompetitionsUseCase:
    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
        league_config_repo: LeagueConfigRepositoryPort,
    ) -> None:
        self._ingest = IngestCompetitionUseCase(provider, repo, scoring)
        self._league_config_repo = league_config_repo

    async def execute(self, season: int, provider_name: str = "api-football") -> list[IngestionResult]:
        results: list[IngestionResult] = []
        leagues = await self._league_config_repo.get_all_active_leagues(provider_name)
        for league in leagues:
            if self._ingest._provider.requests_used >= 7000:
                break
            result = await self._ingest.execute(league, season)
            results.append(result)
        return results
