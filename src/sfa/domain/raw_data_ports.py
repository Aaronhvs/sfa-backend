from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sfa.domain.enrichment_ports import PlayerEnrichDTO
from sfa.domain.ingestion_ports import FixtureEventRawDTO
from sfa.infrastructure.models.enums import Position


@dataclass(frozen=True)
class RawPlayerStatsDTO:
    player_id: int
    fixture_id: int
    competition_id: int
    season: str
    player_name: str
    position: Position
    goals: int
    assists: int
    shots_on: int
    passes_key: int
    dribbles_success: int
    duels_won: int
    tackles: int
    interceptions: int
    blocks: int
    minutes: int
    is_away: bool
    rival_position: int
    player_team_position: int
    stage_factor: float
    home_team_external_id: int
    fixture_events: list[FixtureEventRawDTO]


@runtime_checkable
class RawDataRepositoryPort(Protocol):
    async def get_raw_stats_for_calculation(
        self,
        competition_id: int,
        season: str,
        player_ids: list[int] | None = None,
    ) -> list[RawPlayerStatsDTO]: ...

    async def get_fixture_events_raw(
        self, fixture_id: int,
    ) -> list[FixtureEventRawDTO]: ...

    async def get_players_in_competition(
        self, competition_id: int, season: str,
    ) -> list[PlayerEnrichDTO]: ...

    async def get_downloaded_fixture_ids(
        self, competition_id: int, season: str,
    ) -> set[int]: ...
