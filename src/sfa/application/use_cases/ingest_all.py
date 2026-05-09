from __future__ import annotations

from sfa.application.use_cases.ingest_competition import IngestCompetitionUseCase, IngestionResult
from sfa.domain.ingestion_ports import LEAGUES, FootballDataProviderPort, IngestionRepositoryPort
from sfa.domain.scoring.services import SFAScoringService


class IngestAllCompetitionsUseCase:
    """DEPRECATED: use DownloadPlayerDataUseCase + CalculateSFAFromRawUseCase instead. Will be removed in next refactor."""

    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._ingest = IngestCompetitionUseCase(provider, repo, scoring)

    async def execute(self, season: int) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        for league in LEAGUES:
            if self._ingest._provider.requests_used >= 7000:
                break
            result = await self._ingest.execute(league, season)
            results.append(result)
        return results
