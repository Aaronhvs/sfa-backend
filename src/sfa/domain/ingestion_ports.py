from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position

# ---------------------------------------------------------------------------
# Raw DTOs — data as it arrives from the API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StandingRawDTO:
    team_external_id: int
    team_name: str
    position: int
    points: int
    played: int


@dataclass(frozen=True)
class FixtureRawDTO:
    external_id: int
    home_team_external_id: int
    away_team_external_id: int
    home_team_name: str
    away_team_name: str
    round_str: str
    league_name: str
    played_at: datetime
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class FixtureEventRawDTO:
    type: str
    detail: str
    player_name: str
    assist_name: str | None
    team_external_id: int
    minute: int
    extra_minute: int


@dataclass(frozen=True)
class PlayerStatsRawDTO:
    player_external_id: int
    player_name: str
    position: str
    minutes: int
    goals: int
    assists: int
    shots_on: int
    passes_key: int
    dribbles_success: int
    duels_won: int
    tackles: int
    interceptions: int
    blocks: int
    photo_url: str | None = None


# ---------------------------------------------------------------------------
# League configuration — domain config, shared across multiple use cases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeagueConfig:
    id: int
    name: str
    country: str
    comp_factor: float
    top_n: int


LEAGUES: list[LeagueConfig] = [
    LeagueConfig(id=140, name="La Liga",          country="ESP", comp_factor=1.0, top_n=6),
    LeagueConfig(id=39,  name="Premier League",   country="ENG", comp_factor=1.0, top_n=6),
    LeagueConfig(id=78,  name="Bundesliga",       country="GER", comp_factor=1.0, top_n=6),
    LeagueConfig(id=135, name="Serie A",          country="ITA", comp_factor=1.0, top_n=6),
    LeagueConfig(id=61,  name="Ligue 1",          country="FRA", comp_factor=1.0, top_n=6),
    LeagueConfig(id=2,   name="Champions League", country="EUR", comp_factor=1.5, top_n=24),
]

UCL_LEAGUE_ID = 2


# ---------------------------------------------------------------------------
# Result DTOs — operation outcomes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DownloadResult:
    competition: str
    fixtures_downloaded: int
    fixtures_skipped: int
    players_downloaded: int
    requests_used: int
    status: str
    error: str | None


@dataclass(frozen=True)
class CalculationResult:
    competition_id: int
    season: str
    players_calculated: int
    events_created: int
    scores_updated: int
    status: str
    error: str | None


@dataclass(frozen=True)
class RequestEstimationResult:
    total_estimated_requests: int
    fixtures_already_downloaded: int
    fixtures_pending: int
    net_new_requests: int
    daily_limit: int
    is_feasible: bool


# ---------------------------------------------------------------------------
# Domain service — request estimation (pure, no I/O)
# ---------------------------------------------------------------------------


class RequestEstimationService:
    """Estimates API-Football requests needed before executing a download.

    Expected defaults per league type:
    - Domestic leagues: 38 fixtures
    - Champions League (id=2): 10 fixtures per team in the tracked set
    """

    DAILY_LIMIT = 100
    DEFAULT_FIXTURES_DOMESTIC = 38
    DEFAULT_FIXTURES_UCL = 10

    def estimate(
        self,
        leagues: list[LeagueConfig],
        already_downloaded_count: int,
        fixtures_per_league: dict[int, int],
    ) -> RequestEstimationResult:
        total_estimated = 0
        fixtures_pending = 0
        net_new = 0

        for league in leagues:
            expected = (
                self.DEFAULT_FIXTURES_UCL
                if league.id == UCL_LEAGUE_ID
                else self.DEFAULT_FIXTURES_DOMESTIC
            )
            downloaded = fixtures_per_league.get(league.id, 0)
            pending = max(0, expected - downloaded)

            total_estimated += 2 * expected
            fixtures_pending += pending

            if pending > 0:
                # 2 requests per fixture (events + players) + 2 overhead (standings + team-fixtures)
                net_new += 2 * pending + 2

        return RequestEstimationResult(
            total_estimated_requests=total_estimated,
            fixtures_already_downloaded=already_downloaded_count,
            fixtures_pending=fixtures_pending,
            net_new_requests=net_new,
            daily_limit=self.DAILY_LIMIT,
            is_feasible=net_new <= self.DAILY_LIMIT,
        )


# ---------------------------------------------------------------------------
# Ports (Protocols)
# ---------------------------------------------------------------------------


@runtime_checkable
class FootballDataProviderPort(Protocol):
    async def fetch_standings(
        self, league_id: int, season: int,
    ) -> list[StandingRawDTO]: ...

    async def fetch_team_fixtures(
        self, team_id: int, league_id: int, season: int,
    ) -> list[FixtureRawDTO]: ...

    async def fetch_fixture_events(
        self, fixture_id: int,
    ) -> list[FixtureEventRawDTO]: ...

    async def fetch_fixture_players(
        self, fixture_id: int,
    ) -> dict[int, list[PlayerStatsRawDTO]]: ...

    def get_stage(self, round_str: str, league_name: str) -> str: ...


@runtime_checkable
class IngestionRepositoryPort(Protocol):
    async def upsert_competition(
        self, name: str, country: str, factor: float,
    ) -> int: ...

    async def upsert_team(
        self, external_id: int, name: str, competition_id: int,
    ) -> int: ...

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
        photo_url: str | None = None,
    ) -> int: ...

    async def upsert_fixture(
        self, external_id: int, competition_id: int,
        home_team_id: int, away_team_id: int,
        stage: str, season: str, played_at: datetime,
        matchday: int | None,
    ) -> int: ...

    async def upsert_standing_snapshot(
        self, competition_id: int, team_id: int,
        season: str, matchday: int, position: int, points: int,
    ) -> None: ...

    async def upsert_player_event(
        self, player_id: int, fixture_id: int,
        minute: int, event_type: EventType,
        score_before: str | None, score_diff: int | None,
        psxg: float | None,
        m1: float, m2: float, m3: float, m4: float,
        mvisit: float, pts: float,
    ) -> None: ...

    async def upsert_player_stats(
        self, player_id: int, fixture_id: int,
        season: str, stats: dict,
    ) -> None: ...

    async def upsert_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float,
        matches_played: int, breakdown: dict,
    ) -> None: ...

    async def get_stage_factor(
        self, competition_id: int, stage: str,
    ) -> float: ...

    async def save_ingestion_log(
        self, competition_id: int, season: str,
        status: IngestionStatus, players_processed: int | None,
        error_msg: str | None,
    ) -> None: ...

    async def delete_player_events_for_fixture(
        self, player_id: int, fixture_id: int,
    ) -> None: ...

    async def fixture_players_already_downloaded(
        self, fixture_id: int,
    ) -> bool: ...


@runtime_checkable
class DownloadPlayerDataUseCaseProtocol(Protocol):
    async def execute(
        self,
        league: LeagueConfig,
        season: int,
        player_filter: list[str] | None = None,
    ) -> DownloadResult: ...


@runtime_checkable
class CalculateSFAFromRawUseCaseProtocol(Protocol):
    async def execute(
        self,
        competition_id: int,
        season: str,
        player_ids: list[int] | None = None,
    ) -> CalculationResult: ...
