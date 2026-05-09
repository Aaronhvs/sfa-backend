from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
from sfa.domain.ingestion_ports import (
    FixtureEventRawDTO,
    FixtureRawDTO,
    FootballDataProviderPort,
    IngestionRepositoryPort,
    LeagueConfig,
    PlayerStatsRawDTO,
    StandingRawDTO,
)
from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEAGUE = LeagueConfig(id=140, name="La Liga", country="ESP", comp_factor=1.0, top_n=1)
_SEASON = 2024

_STANDING = StandingRawDTO(
    team_external_id=1001, team_name="FC Test", position=1, points=80, played=34
)

_FIXTURE = FixtureRawDTO(
    external_id=9001,
    home_team_external_id=1001,
    away_team_external_id=1002,
    home_team_name="FC Test",
    away_team_name="Rival FC",
    round_str="Regular Season - 34",
    league_name="La Liga",
    played_at=datetime(2024, 5, 1, 20, 0, tzinfo=timezone.utc),
    home_goals=2,
    away_goals=1,
)

_PLAYER_HOME = PlayerStatsRawDTO(
    player_external_id=501,
    player_name="Lamine Yamal",
    position="Forward",
    minutes=90,
    goals=1,
    assists=0,
    shots_on=3,
    passes_key=2,
    dribbles_success=4,
    duels_won=5,
    tackles=1,
    interceptions=0,
    blocks=0,
    photo_url="https://media.api-sports.io/football/players/501.png",
)

_PLAYER_AWAY = PlayerStatsRawDTO(
    player_external_id=502,
    player_name="Other Player",
    position="Midfielder",
    minutes=90,
    goals=0,
    assists=1,
    shots_on=1,
    passes_key=3,
    dribbles_success=2,
    duels_won=4,
    tackles=2,
    interceptions=1,
    blocks=0,
    photo_url=None,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeFootballDataProvider(FootballDataProviderPort):
    def __init__(
        self,
        standings: list[StandingRawDTO] | None = None,
        fixtures: list[FixtureRawDTO] | None = None,
        fixture_players: dict[int, list[PlayerStatsRawDTO]] | None = None,
    ) -> None:
        self._standings = standings if standings is not None else [_STANDING]
        self._fixtures = fixtures if fixtures is not None else [_FIXTURE]
        self._fixture_players: dict[int, list[PlayerStatsRawDTO]] = (
            fixture_players
            if fixture_players is not None
            else {
                _FIXTURE.home_team_external_id: [_PLAYER_HOME],
                _FIXTURE.away_team_external_id: [_PLAYER_AWAY],
            }
        )
        self.events_calls: list[int] = []
        self.players_calls: list[int] = []

    async def fetch_standings(self, league_id: int, season: int) -> list[StandingRawDTO]:
        return self._standings

    async def fetch_team_fixtures(
        self, team_id: int, league_id: int, season: int
    ) -> list[FixtureRawDTO]:
        return self._fixtures

    async def fetch_fixture_events(self, fixture_id: int) -> list[FixtureEventRawDTO]:
        self.events_calls.append(fixture_id)
        return []

    async def fetch_fixture_players(
        self, fixture_id: int
    ) -> dict[int, list[PlayerStatsRawDTO]]:
        self.players_calls.append(fixture_id)
        return self._fixture_players

    def get_stage(self, round_str: str, league_name: str) -> str:
        return "regular"


class FakeIngestionRepository(IngestionRepositoryPort):
    def __init__(self, fixture_already_downloaded: bool = False) -> None:
        self._fixture_already_downloaded = fixture_already_downloaded
        self.competitions: list[dict] = []
        self.teams: list[dict] = []
        self.players: list[dict] = []
        self.player_stats: list[dict] = []
        self.fixtures: list[dict] = []
        self.snapshots: list[dict] = []
        self.season_scores: list[dict] = []
        self.logs: list[dict] = []
        self._fixture_counter = 100

    async def upsert_competition(self, name: str, country: str, factor: float) -> int:
        self.competitions.append({"name": name, "country": country, "factor": factor})
        return 1

    async def upsert_team(self, external_id: int, name: str, competition_id: int) -> int:
        self.teams.append({"external_id": external_id, "name": name})
        return external_id

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
        photo_url: str | None = None,
    ) -> int:
        self.players.append({
            "external_id": external_id, "name": name,
            "team_id": team_id, "position": position, "photo_url": photo_url,
        })
        return external_id

    async def upsert_fixture(
        self, external_id: int, competition_id: int,
        home_team_id: int, away_team_id: int,
        stage: str, season: str, played_at: object, matchday: int | None,
    ) -> int:
        self._fixture_counter += 1
        self.fixtures.append({"external_id": external_id, "db_id": self._fixture_counter})
        return self._fixture_counter

    async def upsert_standing_snapshot(
        self, competition_id: int, team_id: int,
        season: str, matchday: int, position: int, points: int,
    ) -> None:
        self.snapshots.append({"team_id": team_id, "position": position})

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
        self, player_id: int, fixture_id: int, season: str, stats: dict,
    ) -> None:
        self.player_stats.append({
            "player_id": player_id, "fixture_id": fixture_id, "stats": stats
        })

    async def upsert_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float, matches_played: int, breakdown: dict,
    ) -> None:
        self.season_scores.append({"player_id": player_id, "total_pts": total_pts})

    async def get_stage_factor(self, competition_id: int, stage: str) -> float:
        return 1.0

    async def save_ingestion_log(
        self, competition_id: int, season: str,
        status: IngestionStatus, players_processed: int | None, error_msg: str | None,
    ) -> None:
        self.logs.append({"status": status, "players": players_processed})

    async def delete_player_events_for_fixture(self, player_id: int, fixture_id: int) -> None:
        pass

    async def fixture_players_already_downloaded(self, fixture_id: int) -> bool:
        return self._fixture_already_downloaded


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDownloadPlayerDataUseCase:

    @pytest.mark.anyio
    async def test_download_normal_returns_correct_result(self):
        provider = FakeFootballDataProvider()
        repo = FakeIngestionRepository(fixture_already_downloaded=False)
        uc = DownloadPlayerDataUseCase(provider, repo)

        result = await uc.execute(_LEAGUE, _SEASON)

        assert result.status == "completed"
        assert result.fixtures_downloaded == 1
        assert result.fixtures_skipped == 0
        assert result.players_downloaded == 2
        assert result.error is None
        # standings(1) + team_fixtures(1) + events(1) + players(1) = 4
        assert result.requests_used == 4

    @pytest.mark.anyio
    async def test_already_downloaded_fixture_is_skipped(self):
        provider = FakeFootballDataProvider()
        repo = FakeIngestionRepository(fixture_already_downloaded=True)
        uc = DownloadPlayerDataUseCase(provider, repo)

        result = await uc.execute(_LEAGUE, _SEASON)

        assert result.fixtures_skipped == 1
        assert result.fixtures_downloaded == 0
        assert result.players_downloaded == 0
        # No events or players calls made
        assert provider.events_calls == []
        assert provider.players_calls == []

    @pytest.mark.anyio
    async def test_player_filter_excludes_non_matching_players(self):
        provider = FakeFootballDataProvider()
        repo = FakeIngestionRepository(fixture_already_downloaded=False)
        uc = DownloadPlayerDataUseCase(provider, repo)

        result = await uc.execute(_LEAGUE, _SEASON, player_filter=["Yamal"])

        # Only Lamine Yamal matches "Yamal"
        assert result.players_downloaded == 1
        assert len(repo.player_stats) == 1
        assert repo.player_stats[0]["player_id"] == _PLAYER_HOME.player_external_id

    @pytest.mark.anyio
    async def test_photo_url_persisted_on_player_and_stats(self):
        provider = FakeFootballDataProvider()
        repo = FakeIngestionRepository(fixture_already_downloaded=False)
        uc = DownloadPlayerDataUseCase(provider, repo)

        await uc.execute(_LEAGUE, _SEASON, player_filter=["Yamal"])

        player_record = next(p for p in repo.players if p["name"] == "Lamine Yamal")
        stats_record = next(s for s in repo.player_stats if s["player_id"] == _PLAYER_HOME.player_external_id)

        assert player_record["photo_url"] == _PLAYER_HOME.photo_url
        assert stats_record["stats"]["photo_url"] == _PLAYER_HOME.photo_url

    @pytest.mark.anyio
    async def test_empty_standings_returns_completed_with_zeros(self):
        provider = FakeFootballDataProvider(standings=[])
        repo = FakeIngestionRepository()
        uc = DownloadPlayerDataUseCase(provider, repo)

        result = await uc.execute(_LEAGUE, _SEASON)

        assert result.status == "completed"
        assert result.fixtures_downloaded == 0
        assert result.players_downloaded == 0
