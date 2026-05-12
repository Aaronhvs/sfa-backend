from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sfa.infrastructure.models.enums import Position


class PositionGroup(str, Enum):
    FW = "FW"  # DEL, EXT
    MF = "MF"  # MC
    DF = "DF"  # DC, LAT


def position_to_group(position: Position) -> PositionGroup:
    """Translate a player Position to a PositionGroup for scoring purposes.

    Raises ValueError for GK since goalkeeper scoring is not defined.
    """
    mapping: dict[Position, PositionGroup] = {
        Position.DEL: PositionGroup.FW,
        Position.EXT: PositionGroup.FW,
        Position.MC: PositionGroup.MF,
        Position.DC: PositionGroup.DF,
        Position.LAT: PositionGroup.DF,
    }
    if position not in mapping:
        raise ValueError(f"No scoring group defined for position: {position!r}")
    return mapping[position]


class ActionType(str, Enum):
    GOAL = "goal"
    GOAL_PENALTY = "goal_penalty"
    ASSIST = "assist"
    CORNER_ASSIST = "corner_assist"
    XG_NO_GOAL = "xg_no_goal"
    XA_NO_ASSIST = "xa_no_assist"
    DRIBBLES_WON = "dribbles_won"
    DUELS_WON = "duels_won"
    TACKLES_INTERCEPTIONS = "tackles_interceptions"
    BLOCKS = "blocks"
    PROGRESSIVE_PASSES = "progressive_passes"
    PROGRESSIVE_CARRIES = "progressive_carries"
    PRESSURES_SUCCESS = "pressures_success"
    RECOVERIES_OPP_HALF = "recoveries_opp_half"
    CLEARANCES_GOAL_LINE = "clearances_goal_line"


@dataclass(frozen=True)
class M1RivalDifficulty:
    """
    M1 = 1.0 + (player_team_pos - rival_team_pos) / 20
    Clamped to [0.5, 2.0].
    """

    value: float

    def __init__(self, player_team_pos: int, rival_team_pos: int) -> None:
        raw = 1.0 + (player_team_pos - rival_team_pos) / 20.0
        clamped = max(0.5, min(2.0, raw))
        object.__setattr__(self, "value", clamped)


@dataclass(frozen=True)
class M2CompetitionStage:
    """Wraps the stage_factor stored in CompetitionStage.stage_factor."""

    value: float

    def __init__(self, stage_factor: float) -> None:
        if stage_factor <= 0:
            raise ValueError(f"stage_factor must be > 0, got {stage_factor}")
        object.__setattr__(self, "value", float(stage_factor))


@dataclass(frozen=True)
class M3MinuteScore:
    """
    Context multiplier based on match minute and score differential.

    score_diff = player_team_goals - rival_goals at the moment of the action.
    Negative  → losing
    Zero      → drawing
    Positive  → winning

    Penalties use the same minute/score logic as regular goals — their lower
    base_pts already encode the reduced value of a penalty goal.
    """

    value: float

    def __init__(self, minute: int, score_diff: int) -> None:
        if 80 <= minute <= 90:
            if score_diff <= 0:
                v = 2.5
            elif score_diff == 1:
                v = 1.4
            else:  # score_diff >= 2
                v = 0.7
        elif 70 <= minute <= 79:
            if score_diff == 0:
                v = 1.8
            elif score_diff < 0:
                v = 1.6
            else:
                v = 1.0
        elif 45 <= minute <= 69:
            if score_diff < 0:
                v = 1.3
            elif score_diff == 0:
                v = 1.2
            else:
                v = 1.0
        elif 1 <= minute <= 44:
            v = 1.0
        else:
            raise ValueError(f"minute must be in [1, 90], got {minute}")
        object.__setattr__(self, "value", v)


@dataclass(frozen=True)
class M4ShotDifficulty:
    """
    M4 = 1.0 + (1.0 - PSxG) * 0.8   clamped to [1.0, 1.8]
    Only meaningful for goals/shots. When psxg is None, value is 1.0.
    """

    value: float

    def __init__(self, psxg: float | None = None) -> None:
        if psxg is None:
            object.__setattr__(self, "value", 1.0)
        else:
            raw = 1.0 + (1.0 - psxg) * 0.8
            clamped = max(1.0, min(1.8, raw))
            object.__setattr__(self, "value", clamped)


@dataclass(frozen=True)
class MvisitFactor:
    """
    Away bonus: ×1.3 for goals or assists scored away from home.
    Applies only to goals and assists; all other events use ×1.0.
    """

    value: float

    def __init__(self, is_away: bool, is_goal_or_assist: bool) -> None:
        v = 1.3 if (is_away and is_goal_or_assist) else 1.0
        object.__setattr__(self, "value", v)


@dataclass(frozen=True)
class CombinedMultiplier:
    """
    Product of all context multipliers, clamped to [0.3, 4.0].
    """

    value: float

    def __init__(
        self,
        m1: M1RivalDifficulty,
        m2: M2CompetitionStage,
        m3: M3MinuteScore,
        m4: M4ShotDifficulty,
        mvisit: MvisitFactor,
    ) -> None:
        raw = m1.value * m2.value * m3.value * m4.value * mvisit.value
        clamped = max(0.3, min(4.0, raw))
        object.__setattr__(self, "value", clamped)


@dataclass(frozen=True)
class SFAScore:
    """Final score for a single action."""

    base_pts: float
    multiplier: CombinedMultiplier
    total: float

    def __init__(self, base_pts: float, multiplier: CombinedMultiplier) -> None:
        object.__setattr__(self, "base_pts", base_pts)
        object.__setattr__(self, "multiplier", multiplier)
        object.__setattr__(self, "total", base_pts * multiplier.value)
