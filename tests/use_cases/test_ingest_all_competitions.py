# Pre-existing failures before writing this file: none (33 passed).
from __future__ import annotations

from datetime import datetime

import pytest

from sfa.application.use_cases.ingest_all import IngestAllCompetitionsUseCase
from sfa.domain.ingestion_ports import (
    FixtureEventRawDTO,
    FixtureRawDTO,
    FootballDataProviderPort,
    IngestionRepositoryPort,
    LeagueConfigDTO,
    LeagueConfigRepositoryPort,
    PlayerStatsRawDTO,
    StandingRawDTO,
)
from sfa.domain.scoring.services import SFAScoringService
from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLeagueConfigRepository(LeagueConfigRepositoryPort):
    def __init__(self, leagues: list[LeagueConfigDTO] | None = None) -> None:
        self._leagues = leagues or []

    async def get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]:
        return self._leagues

    async def get_league_by_external_id(
        self, provider_name: str, external_id: int,
    ) -> LeagueConfigDTO | None:
        return next((l for l in self._leagues if l.external_id == external_id), None)


class FakeProvider(FootballDataProviderPort):
    def __init__(self, requests_used: int = 0) -> None:
        self.requests_used = requests_used

    async def fetch_standings(self, league_id: int, season: int) -> list[StandingRawDTO]:
        return []

    async def fetch_team_fixtures(
        self, team_id: int, league_id: int, season: int,
    ) -> list[FixtureRawDTO]:
        return []

    async def fetch_fixture_events(self, fixture_id: int) -> list[FixtureEventRawDTO]:
        return []

    async def fetch_fixture_players(
        self, fixture_id: int, team_id: int,
    ) -> list[PlayerStatsRawDTO]:
        return []

    def get_stage(self, round_str: str, league_name: str) -> str:
        return "Regular Season"

    def get_score_at_minute(self, events, minute, home_team_ext_id):
        return 0, 0


class FakeIngestionRepository(IngestionRepositoryPort):
    async def upsert_competition(self, name: str, country: str, factor: float) -> int:
        return 1

    async def upsert_team(self, external_id: int, name: str, competition_id: int) -> int:
        return 1

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
    ) -> int:
        return 1

    async def upsert_fixture(
        self, external_id: int, competition_id: int,
        home_team_id: int, away_team_id: int,
        stage: str, season: str, played_at: datetime,
        matchday: int | None,
    ) -> int:
        return 1

    async def upsert_standing_snapshot(
        self, competition_id: int, team_id: int,
        season: str, matchday: int, position: int, points: int,
    ) -> None:
        pass

    async def upsert_player_event(
        self, player_id: int, fixture_id: int,
        minute: int, event_type: EventType,
        score_before: str | None, score_diff: int | None,
        psxg: float | None,
        m1: float, m2: float, m3: float, m4: float,
        mvisit: float, pts: float,
    ) -> None:
        pass

    async def upsert_player_stats(
        self, player_id: int, fixture_id: int,
        season: str, stats: dict,
    ) -> None:
        pass

    async def upsert_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float,
        matches_played: int, breakdown: dict,
    ) -> None:
        pass

    async def get_stage_factor(self, competition_id: int, stage: str) -> float:
        return 1.0

    async def save_ingestion_log(
        self, competition_id: int, season: str,
        status: IngestionStatus, players_processed: int | None,
        error_msg: str | None,
    ) -> None:
        pass

    async def delete_player_events_for_fixture(
        self, player_id: int, fixture_id: int,
    ) -> None:
        pass


def _make_league(competition_id: int, external_id: int, name: str = "League") -> LeagueConfigDTO:
    return LeagueConfigDTO(
        competition_id=competition_id,
        external_id=external_id,
        name=name,
        country="ESP",
        comp_factor=1.0,
        top_n=6,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFakeLeagueConfigRepositoryProtocol:
    def test_isinstance_check(self):
        assert isinstance(FakeLeagueConfigRepository(), LeagueConfigRepositoryPort)


class TestIngestAllCompetitionsUseCase:
    @pytest.mark.anyio
    async def test_execute_iterates_all_active_leagues(self):
        leagues = [_make_league(1, 140, "La Liga"), _make_league(2, 39, "Premier League")]
        league_repo = FakeLeagueConfigRepository(leagues)
        provider = FakeProvider(requests_used=0)
        repo = FakeIngestionRepository()
        scoring = SFAScoringService()

        use_case = IngestAllCompetitionsUseCase(provider, repo, scoring, league_repo)
        results = await use_case.execute(season=2024)

        assert len(results) == 2
        assert results[0].competition == "La Liga"
        assert results[1].competition == "Premier League"

    @pytest.mark.anyio
    async def test_execute_respects_requests_limit(self):
        leagues = [
            _make_league(1, 140, "La Liga"),
            _make_league(2, 39, "Premier League"),
            _make_league(3, 78, "Bundesliga"),
        ]
        league_repo = FakeLeagueConfigRepository(leagues)
        provider = FakeProvider(requests_used=7000)
        repo = FakeIngestionRepository()
        scoring = SFAScoringService()

        use_case = IngestAllCompetitionsUseCase(provider, repo, scoring, league_repo)
        results = await use_case.execute(season=2024)

        assert len(results) == 0

    @pytest.mark.anyio
    async def test_get_league_by_external_id_returns_none_for_unknown(self):
        league_repo = FakeLeagueConfigRepository([])
        result = await league_repo.get_league_by_external_id("api-football", 9999)
        assert result is None
