from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sfa.domain.ingestion_ports import (
    CalculationResult,
    FixtureEventRawDTO,
    IngestionRepositoryPort,
)
from sfa.domain.raw_data_ports import RawDataRepositoryPort, RawPlayerStatsDTO
from sfa.domain.scoring.services import BASE_POINTS_TABLE, SFAScoringService
from sfa.domain.scoring.value_objects import (
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
from sfa.infrastructure.models.enums import EventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _PlayerAccum:
    total_pts: float = 0.0
    matches_played: int = 0
    total_minutes: int = 0
    events_created: int = 0
    breakdown: dict = field(default_factory=dict)


def _name_matches(event_name: str | None, stats_name: str) -> bool:
    if not event_name:
        return False
    a = event_name.lower().strip()
    b = stats_name.lower().strip()
    return a == b or a in b or b in a


def _add_to_breakdown(breakdown: dict, key: str, pts: float) -> None:
    if key not in breakdown:
        breakdown[key] = {"count": 0, "pts": 0.0}
    breakdown[key]["count"] += 1
    breakdown[key]["pts"] = round(breakdown[key]["pts"] + pts, 2)


def _is_player_team_event(
    evt: FixtureEventRawDTO, is_away: bool, home_team_ext_id: int,
) -> bool:
    if is_away:
        return evt.team_external_id != home_team_ext_id
    return evt.team_external_id == home_team_ext_id


def _get_score_at_minute(
    events: list[FixtureEventRawDTO],
    minute: int,
    home_team_ext_id: int,
) -> tuple[int, int]:
    """Return (home_goals, away_goals) scored strictly before the given minute."""
    home_goals = 0
    away_goals = 0
    for e in events:
        event_minute = e.minute + e.extra_minute
        if event_minute >= minute:
            continue
        if e.type != "Goal" or e.detail == "Missed Penalty":
            continue
        if e.detail == "Own Goal":
            if e.team_external_id == home_team_ext_id:
                away_goals += 1
            else:
                home_goals += 1
        else:
            if e.team_external_id == home_team_ext_id:
                home_goals += 1
            else:
                away_goals += 1
    return home_goals, away_goals


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class CalculateSFAFromRawUseCase:
    """Computes SFA scoring from already-downloaded RAW player stats.

    Responsibilities:
    - Read raw player stats from RawDataRepositoryPort
    - Score events (goals/assists) with full M1–M4+Mvisit context
    - Score match-level stats (duels, tackles, etc.) with M1+M2 context
    - Persist player_events (idempotent) and sfa_season_scores

    NOT responsible for:
    - Downloading data from any external API
    - Fetching standings, fixtures, or player stats from API-Football
    """

    def __init__(
        self,
        raw_repo: RawDataRepositoryPort,
        ingestion_repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._raw_repo = raw_repo
        self._ingestion_repo = ingestion_repo
        self._scoring = scoring

    async def execute(
        self,
        competition_id: int,
        season: str,
        player_ids: list[int] | None = None,
    ) -> CalculationResult:
        player_accum: dict[int, _PlayerAccum] = {}
        total_events_created = 0

        try:
            raw_stats = await self._raw_repo.get_raw_stats_for_calculation(
                competition_id, season, player_ids
            )

            for dto in raw_stats:
                try:
                    group = position_to_group(dto.position)
                except ValueError:
                    continue  # GK: no scoring group defined

                player_id = dto.player_id
                if player_id not in player_accum:
                    player_accum[player_id] = _PlayerAccum()
                accum = player_accum[player_id]
                accum.total_minutes += dto.minutes
                accum.matches_played += 1

                await self._ingestion_repo.delete_player_events_for_fixture(
                    player_id, dto.fixture_id
                )

                n_events = await self._score_events(dto=dto, group=group, accum=accum)
                accum.events_created += n_events
                total_events_created += n_events

                stats_for_scoring = {
                    ActionType.DUELS_WON: dto.duels_won,
                    ActionType.TACKLES_INTERCEPTIONS: dto.tackles + dto.interceptions,
                    ActionType.BLOCKS: dto.blocks,
                    ActionType.DRIBBLES_WON: dto.dribbles_success,
                }
                stats_total = 0.0
                for s in self._scoring.score_match_stats(
                    group, stats_for_scoring,
                    dto.player_team_position, dto.rival_position, dto.stage_factor,
                ):
                    accum.total_pts += s.total
                    stats_total += s.total
                    _add_to_breakdown(accum.breakdown, "stats", s.total)

                if stats_total > 0:
                    m1_val = M1RivalDifficulty(dto.player_team_position, dto.rival_position).value
                    m2_val = M2CompetitionStage(dto.stage_factor).value
                    await self._ingestion_repo.upsert_player_event(
                        dto.player_id, dto.fixture_id,
                        90, EventType.STATS,
                        None, None, None,
                        m1_val, m2_val, 1.0, 1.0, 1.0,
                        round(stats_total, 2),
                    )
                    accum.events_created += 1
                    total_events_created += 1

            scores_updated = 0
            for player_id, accum in player_accum.items():
                if accum.total_minutes < 90:
                    continue

                total = accum.total_pts
                for key in accum.breakdown:
                    pct = round(accum.breakdown[key]["pts"] / total * 100, 1) if total > 0 else 0.0
                    accum.breakdown[key]["pct"] = pct

                await self._ingestion_repo.upsert_season_score(
                    player_id, competition_id, season,
                    round(accum.total_pts, 2),
                    accum.matches_played,
                    accum.breakdown,
                )
                scores_updated += 1

            return CalculationResult(
                competition_id=competition_id,
                season=season,
                players_calculated=len(player_accum),
                events_created=total_events_created,
                scores_updated=scores_updated,
                status="completed",
                error=None,
            )

        except Exception as exc:
            logger.exception(
                "[CalculateSFAFromRawUseCase] Failed for competition_id=%s season=%s",
                competition_id, season,
            )
            return CalculationResult(
                competition_id=competition_id,
                season=season,
                players_calculated=len(player_accum),
                events_created=total_events_created,
                scores_updated=0,
                status="failed",
                error=str(exc),
            )

    async def _score_events(
        self,
        dto: RawPlayerStatsDTO,
        group: PositionGroup,
        accum: _PlayerAccum,
    ) -> int:
        events_created = 0

        player_goals = [
            e for e in dto.fixture_events
            if e.type == "Goal"
            and e.detail not in ("Missed Penalty", "Own Goal")
            and _name_matches(e.player_name, dto.player_name)
            and _is_player_team_event(e, dto.is_away, dto.home_team_external_id)
        ]
        for evt in player_goals:
            events_created += await self._process_event(
                accum=accum, evt=evt, all_events=dto.fixture_events,
                player_id=dto.player_id, fixture_id=dto.fixture_id,
                group=group,
                player_team_pos=dto.player_team_position,
                rival_pos=dto.rival_position,
                stage_factor=dto.stage_factor,
                is_away=dto.is_away,
                home_team_ext_id=dto.home_team_external_id,
                is_assist=False,
            )

        player_assists = [
            e for e in dto.fixture_events
            if e.type == "Goal"
            and e.detail not in ("Missed Penalty", "Own Goal")
            and e.assist_name is not None
            and _name_matches(e.assist_name, dto.player_name)
            and _is_player_team_event(e, dto.is_away, dto.home_team_external_id)
        ]
        for evt in player_assists:
            events_created += await self._process_event(
                accum=accum, evt=evt, all_events=dto.fixture_events,
                player_id=dto.player_id, fixture_id=dto.fixture_id,
                group=group,
                player_team_pos=dto.player_team_position,
                rival_pos=dto.rival_position,
                stage_factor=dto.stage_factor,
                is_away=dto.is_away,
                home_team_ext_id=dto.home_team_external_id,
                is_assist=True,
            )

        return events_created

    async def _process_event(
        self,
        *,
        accum: _PlayerAccum,
        evt: FixtureEventRawDTO,
        all_events: list[FixtureEventRawDTO],
        player_id: int,
        fixture_id: int,
        group: PositionGroup,
        player_team_pos: int,
        rival_pos: int,
        stage_factor: float,
        is_away: bool,
        home_team_ext_id: int,
        is_assist: bool,
    ) -> int:
        minute = evt.minute + evt.extra_minute
        clamped = max(1, min(90, minute))
        is_penalty = evt.detail == "Penalty"

        home_b, away_b = _get_score_at_minute(all_events, minute, home_team_ext_id)
        score_diff = (away_b - home_b) if is_away else (home_b - away_b)
        score_before_str = f"{home_b}:{away_b}"

        if is_assist:
            is_corner = "corner" in evt.detail.lower()
            action = ActionType.CORNER_ASSIST if is_corner else ActionType.ASSIST
            psxg: float | None = None
            event_type = EventType.CORNER_ASSIST if is_corner else EventType.ASSIST
        else:
            action = ActionType.GOAL_PENALTY if is_penalty else ActionType.GOAL
            psxg = 0.32
            event_type = EventType.GOAL_PENALTY if is_penalty else EventType.GOAL

        base_pts = float(BASE_POINTS_TABLE[group][action])
        if base_pts == 0:
            return 0

        m1 = M1RivalDifficulty(player_team_pos, rival_pos)
        m2 = M2CompetitionStage(stage_factor)
        m3 = M3MinuteScore(clamped, score_diff, is_penalty)
        m4 = M4ShotDifficulty(psxg)
        mvisit = MvisitFactor(is_away, True)
        combined = CombinedMultiplier(m1, m2, m3, m4, mvisit)
        sfa = SFAScore(base_pts, combined)

        await self._ingestion_repo.upsert_player_event(
            player_id, fixture_id,
            minute, event_type,
            score_before_str, score_diff, psxg,
            m1.value, m2.value, m3.value, m4.value, mvisit.value,
            round(sfa.total, 2),
        )

        _add_to_breakdown(accum.breakdown, action.value, sfa.total)
        accum.total_pts += sfa.total
        return 1
