from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position


@dataclass(frozen=True)
class LeagueConfigDTO:
    competition_id: int
    external_id: int
    name: str
    country: str
    comp_factor: float
    top_n: int


@runtime_checkable
class LeagueConfigRepositoryPort(Protocol):
    async def get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]: ...

    async def get_league_by_external_id(
        self, provider_name: str, external_id: int,
    ) -> LeagueConfigDTO | None: ...


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
        self, fixture_id: int, team_id: int,
    ) -> list[PlayerStatsRawDTO]: ...


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
