from __future__ import annotations

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
)

# ---------------------------------------------------------------------------
# Base points table — Section 2 of the SFA business-logic document v2.0
# ---------------------------------------------------------------------------
# Entries with 0 pts mean the action does not apply to that position group.
# The table is the single source of truth; SFAScoringService never hard-codes
# points inline.
# ---------------------------------------------------------------------------

BASE_POINTS_TABLE: dict[PositionGroup, dict[ActionType, int]] = {
    PositionGroup.FW: {
        ActionType.GOAL: 500,
        ActionType.GOAL_PENALTY: 300,
        ActionType.ASSIST: 500,
        ActionType.CORNER_ASSIST: 250,
        ActionType.XG_NO_GOAL: 120,
        ActionType.XA_NO_ASSIST: 180,
        ActionType.DRIBBLES_WON: 100,
        ActionType.DUELS_WON: 80,
        ActionType.TACKLES_INTERCEPTIONS: 180,
        ActionType.BLOCKS: 250,
        ActionType.PROGRESSIVE_PASSES: 100,
        ActionType.PROGRESSIVE_CARRIES: 120,
        ActionType.PRESSURES_SUCCESS: 100,
        ActionType.RECOVERIES_OPP_HALF: 150,
        ActionType.CLEARANCES_GOAL_LINE: 1500,
    },
    PositionGroup.MF: {
        ActionType.GOAL: 850,
        ActionType.GOAL_PENALTY: 450,
        ActionType.ASSIST: 650,
        ActionType.CORNER_ASSIST: 350,
        ActionType.XG_NO_GOAL: 220,
        ActionType.XA_NO_ASSIST: 300,
        ActionType.DRIBBLES_WON: 180,
        ActionType.DUELS_WON: 100,
        ActionType.TACKLES_INTERCEPTIONS: 140,
        ActionType.BLOCKS: 180,
        ActionType.PROGRESSIVE_PASSES: 150,
        ActionType.PROGRESSIVE_CARRIES: 160,
        ActionType.PRESSURES_SUCCESS: 130,
        ActionType.RECOVERIES_OPP_HALF: 180,
        ActionType.CLEARANCES_GOAL_LINE: 1200,
    },
    PositionGroup.DF: {
        ActionType.GOAL: 1300,
        ActionType.GOAL_PENALTY: 500,
        ActionType.ASSIST: 950,
        ActionType.CORNER_ASSIST: 450,
        ActionType.XG_NO_GOAL: 350,
        ActionType.XA_NO_ASSIST: 450,
        ActionType.DRIBBLES_WON: 280,
        ActionType.DUELS_WON: 120,
        ActionType.TACKLES_INTERCEPTIONS: 100,
        ActionType.BLOCKS: 120,
        ActionType.PROGRESSIVE_PASSES: 180,
        ActionType.PROGRESSIVE_CARRIES: 220,
        ActionType.PRESSURES_SUCCESS: 120,
        ActionType.RECOVERIES_OPP_HALF: 160,
        ActionType.CLEARANCES_GOAL_LINE: 900,
    },
}

_GOAL_OR_ASSIST_ACTIONS = {
    ActionType.GOAL,
    ActionType.GOAL_PENALTY,
    ActionType.ASSIST,
    ActionType.CORNER_ASSIST,
}


class SFAScoringService:
    """
    Single entry-point for all SFA scoring calculations.

    Two scoring paths exist as described in the business-logic document:

    1. score_event() — individual actions (goals, assists) with full context:
       pts = base_pts × MIN(MAX(M1 × M2 × M3 × M4 × Mvisit, 0.3), 4.0)

    2. score_match_stats() — per-match aggregated stats (xG, duels, etc.),
       where minute/score context is unavailable:
       pts = value × base_pts × MIN(MAX(M1 × M2, 0.3), 4.0)
    """

    def score_event(
        self,
        group: PositionGroup,
        action: ActionType,
        player_team_pos: int,
        rival_team_pos: int,
        stage_factor: float,
        minute: int,
        score_diff: int,
        psxg: float | None,
        is_away: bool,
    ) -> SFAScore:
        """Calculate the SFA score for a single event (goal or assist).

        All five context multipliers (M1–M4 + Mvisit) are applied.
        The combined multiplier is clamped to [0.3, 4.0].
        """
        base_pts = float(BASE_POINTS_TABLE[group][action])

        is_goal_or_assist = action in _GOAL_OR_ASSIST_ACTIONS

        m1 = M1RivalDifficulty(player_team_pos, rival_team_pos)
        m2 = M2CompetitionStage(stage_factor)
        m3 = M3MinuteScore(minute, score_diff)
        m4 = M4ShotDifficulty(psxg if is_goal_or_assist else None)
        mvisit = MvisitFactor(is_away, is_goal_or_assist)
        combined = CombinedMultiplier(m1, m2, m3, m4, mvisit)

        return SFAScore(base_pts=base_pts, multiplier=combined)

    def score_match_stats(
        self,
        group: PositionGroup,
        stats: dict[ActionType, int | float],
        player_team_pos: int,
        rival_team_pos: int,
        stage_factor: float,
    ) -> list[SFAScore]:
        """Calculate SFA scores for per-match statistics.

        Only M1 and M2 are applied (no minute/score context, no PSxG, no
        home/away bonus) because these actions are match-level aggregates
        without an exact timestamp.

        Returns one SFAScore per action that has a non-zero base_pts and a
        non-zero count/value. Actions not applicable to the position group
        (base_pts == 0) are silently skipped.
        """
        m1 = M1RivalDifficulty(player_team_pos, rival_team_pos)
        m2 = M2CompetitionStage(stage_factor)
        m3 = M3MinuteScore(minute=1, score_diff=0)  # neutral
        m4 = M4ShotDifficulty(psxg=None)  # neutral: 1.0
        mvisit = MvisitFactor(is_away=False, is_goal_or_assist=False)  # neutral: 1.0
        combined = CombinedMultiplier(m1, m2, m3, m4, mvisit)

        scores: list[SFAScore] = []
        for action, count_or_value in stats.items():
            base_per_unit = BASE_POINTS_TABLE[group][action]
            if base_per_unit == 0 or count_or_value == 0:
                continue
            base_pts = float(base_per_unit) * float(count_or_value)
            scores.append(SFAScore(base_pts=base_pts, multiplier=combined))

        return scores
