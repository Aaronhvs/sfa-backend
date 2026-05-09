from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

# ─── DTOs de dominio ─────────────────────────────────────────────────


@dataclass(frozen=True)
class PlayerDTO:
    id: int
    name: str
    position: str
    photo_url: str | None
    team_name: str


@dataclass(frozen=True)
class PlayerScoreDTO:
    """Fila principal de score de un jugador en una season/competition."""
    player_id: int
    player_name: str
    team_name: str
    position: str
    competition_name: str
    competition_id: int
    total_pts: float
    matches_played: int
    photo_url: str | None
    breakdown: dict | None


@dataclass(frozen=True)
class RankedPlayerDTO:
    rank: int
    player_id: int
    player_name: str
    team_name: str
    position: str
    competition_name: str
    total_pts: float
    matches_played: int
    photo_url: str | None


@dataclass(frozen=True)
class PlayerEventDTO:
    id: int
    competition: str
    stage: str
    fixture_id: int
    home_team: str
    away_team: str
    played_at: datetime
    minute: int
    event_type: str
    score_before: str | None
    score_diff: int | None
    m1: float
    m2: float
    m3: float
    m4: float
    mvisit: float
    pts: float


@dataclass(frozen=True)
class PlayerFixtureDTO:
    fixture_id: int
    competition: str
    stage: str
    home_team: str
    away_team: str
    played_at: datetime
    sfa_pts: float
    events_count: int
    minutes: int
    duels_won: int
    dribbles_won: int


@dataclass(frozen=True)
class CompetitionDTO:
    id: int
    name: str
    country: str
    factor: float


@dataclass(frozen=True)
class StandingEntryDTO:
    position: int
    team: str
    points: int


@dataclass(frozen=True)
class SystemCountsDTO:
    players: int
    scores: int
    competitions: int
    events: int
    latest_season: str | None


# ─── Protocols (Ports) ───────────────────────────────────────────────

@runtime_checkable
class PlayerRepositoryProtocol(Protocol):
    async def get_by_id(self, player_id: int) -> PlayerDTO | None: ...
    async def exists(self, player_id: int) -> bool: ...


@runtime_checkable
class SFAScoreRepositoryProtocol(Protocol):
    async def get_best_score_for_player_season(
        self, player_id: int, season: str,
    ) -> PlayerScoreDTO | None:
        """Score row con mayor total_pts para un jugador en una season."""
        ...

    async def get_global_rank(
        self, player_id: int, season: str, total_pts: float,
    ) -> int:
        """Cantidad de jugadores con más pts + 1."""
        ...

    async def get_competitions_for_player_season(
        self, player_id: int, season: str,
    ) -> list[str]:
        """Lista de nombres de competition donde el jugador tiene score."""
        ...

    async def get_ranking(
        self,
        season: str,
        position: str | None = None,
        competition_id: int | None = None,
        limit: int = 50,
    ) -> list[RankedPlayerDTO]: ...

    async def get_ranking_total(
        self,
        season: str,
        position: str | None = None,
        competition_id: int | None = None,
    ) -> int:
        """Total de jugadores en el ranking (sin limit)."""
        ...

    async def latest_season(self) -> str | None: ...

    async def latest_season_for_player(self, player_id: int) -> str | None: ...


@runtime_checkable
class CompetitionRepositoryProtocol(Protocol):
    async def get_all(self) -> list[CompetitionDTO]: ...
    async def get_by_id(self, competition_id: int) -> CompetitionDTO | None: ...


@runtime_checkable
class StandingRepositoryProtocol(Protocol):
    async def get_standings(
        self,
        competition_id: int,
        season: str | None = None,
        matchday: int | None = None,
    ) -> tuple[str, str, int, list[StandingEntryDTO]]:
        """Retorna (competition_name, season, matchday, standings).

        Resuelve season/matchday al más reciente si son None.
        Lanza ValueError si no encuentra data.
        """
        ...


@runtime_checkable
class PlayerEventRepositoryProtocol(Protocol):
    async def get_events_by_player(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerEventDTO]: ...

    async def get_fixtures_by_player(
        self,
        player_id: int,
        season: str | None = None,
        competition_id: int | None = None,
    ) -> list[PlayerFixtureDTO]: ...


@runtime_checkable
class SystemRepositoryProtocol(Protocol):
    async def get_counts(self) -> SystemCountsDTO: ...
