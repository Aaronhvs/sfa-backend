from __future__ import annotations

from dataclasses import dataclass, field

from sfa.infrastructure.models.enums import Position

from .value_objects import (
    ActionType,
    CombinedMultiplier,
    M1RivalDifficulty,
    M2CompetitionStage,
    M3MinuteScore,
    M4ShotDifficulty,
    MvisitFactor,
    PositionGroup,
    SFAScore,
    position_to_group,
)


@dataclass(frozen=True)
class Player:
    id: int
    name: str
    position: Position
    group: PositionGroup

    @classmethod
    def from_position(cls, id: int, name: str, position: Position) -> "Player":
        """Factory that derives the scoring group from the player's position.

        Raises ValueError if position is GK (no scoring group defined).
        """
        group = position_to_group(position)
        return cls(id=id, name=name, position=position, group=group)


@dataclass(frozen=True)
class ScoredEvent:
    """
    Immutable record of a single scored action within a fixture.

    Represents the historical fact that an action occurred in a specific
    context and produced a concrete SFA score.
    """

    fixture_id: int
    minute: int
    action: ActionType
    base_pts: float
    m1: M1RivalDifficulty
    m2: M2CompetitionStage
    m3: M3MinuteScore
    m4: M4ShotDifficulty
    mvisit: MvisitFactor
    combined: CombinedMultiplier
    score: SFAScore


@dataclass
class PlayerSeasonScore:
    """
    Aggregate root that accumulates scored events for a player across a season.

    total_pts is always derived from the stored events — it can never be set
    directly and cannot get out of sync.
    """

    player: Player
    competition_id: int
    season: str
    _events: list[ScoredEvent] = field(default_factory=list, repr=False)

    @property
    def total_pts(self) -> float:
        return sum(e.score.total for e in self._events)

    @property
    def matches_played(self) -> int:
        return len({e.fixture_id for e in self._events})

    def add_events(self, events: list[ScoredEvent]) -> None:
        """Append new events to this season score."""
        self._events.extend(events)

    def replace_fixture_events(
        self, fixture_id: int, events: list[ScoredEvent]
    ) -> None:
        """Replace all events for a given fixture (idempotent re-ingestion)."""
        self._events = [e for e in self._events if e.fixture_id != fixture_id]
        self._events.extend(events)

    def remove_fixture_events(self, fixture_id: int) -> None:
        """Remove all events for a given fixture."""
        self._events = [e for e in self._events if e.fixture_id != fixture_id]
