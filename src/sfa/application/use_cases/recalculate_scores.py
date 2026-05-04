from __future__ import annotations

import logging
from collections import defaultdict

from sfa.domain.enrichment_ports import (
    EnrichmentRepositoryPort,
    RecalculationResult,
)
from sfa.domain.scoring.services import BASE_POINTS_TABLE
from sfa.domain.scoring.value_objects import ActionType, M4ShotDifficulty, position_to_group
from sfa.infrastructure.models.enums import Position

logger = logging.getLogger(__name__)


class RecalculateScoresUseCase:
    def __init__(
        self,
        repo: EnrichmentRepositoryPort,
    ) -> None:
        self._repo = repo

    async def execute(
        self, competition_id: int, season: str,
    ) -> RecalculationResult:
        events_updated = 0
        scores_updated = 0

        # Step 1: Get all events with psxg set (enriched goals/penalties)
        events = await self._repo.get_events_with_psxg_for_recalc(
            competition_id, season
        )

        if not events:
            logger.info(
                "RecalculateScores: no events with psxg for competition_id=%s season=%s",
                competition_id, season,
            )
            return RecalculationResult(events_updated=0, scores_updated=0)

        # Track which players need their season_score updated and their pts delta
        player_deltas: dict[int, float] = defaultdict(float)

        # Step 2: Recalculate M4 and pts for each enriched event
        for event in events:
            try:
                position = Position(event.player_position)
                group = position_to_group(position)
                action = ActionType(event.event_type)
            except ValueError as exc:
                logger.warning(
                    "RecalculateScores: skipping event %d — %s", event.id, exc
                )
                continue

            m4 = M4ShotDifficulty(psxg=event.psxg).value
            raw_combined = event.m1 * event.m2 * event.m3 * m4 * event.mvisit
            combined = max(0.3, min(4.0, raw_combined))

            base_pts = float(BASE_POINTS_TABLE[group][action])
            new_pts = round(base_pts * combined, 2)

            if abs(new_pts - event.current_pts) > 0.01:
                await self._repo.update_event_scores(event.id, m4=m4, pts=new_pts)
                player_deltas[event.player_id] += new_pts - event.current_pts
                events_updated += 1

        # Step 3: Update season_score for each affected player
        for player_id, delta in player_deltas.items():
            current = await self._repo.get_player_season_score_row(
                player_id, competition_id, season
            )
            if current is None:
                logger.warning(
                    "RecalculateScores: no season_score found for "
                    "player_id=%d competition_id=%d season=%s",
                    player_id, competition_id, season,
                )
                continue

            new_total_pts = round(current.total_pts + delta, 2)

            # Rebuild breakdown from all player_events, preserving match stats
            all_events = await self._repo.get_all_player_season_events(
                player_id, competition_id, season
            )

            new_breakdown: dict[str, dict] = {}
            for evt in all_events:
                key = evt.event_type
                if key not in new_breakdown:
                    new_breakdown[key] = {"count": 0, "pts": 0.0}
                new_breakdown[key]["count"] += 1
                new_breakdown[key]["pts"] = round(
                    new_breakdown[key]["pts"] + evt.pts, 2
                )

            # Preserve "stats" entry (match stats points not in player_events)
            if "stats" in current.breakdown:
                new_breakdown["stats"] = current.breakdown["stats"]

            # Recalculate pct
            for key in new_breakdown:
                pct = (
                    round(new_breakdown[key]["pts"] / new_total_pts * 100, 1)
                    if new_total_pts > 0 else 0.0
                )
                new_breakdown[key]["pct"] = pct

            await self._repo.update_season_score(
                player_id=player_id,
                competition_id=competition_id,
                season=season,
                total_pts=new_total_pts,
                matches_played=current.matches_played,
                breakdown=new_breakdown,
            )
            scores_updated += 1

        logger.info(
            "RecalculateScores: events_updated=%d scores_updated=%d "
            "for competition_id=%d season=%s",
            events_updated, scores_updated, competition_id, season,
        )
        return RecalculationResult(
            events_updated=events_updated,
            scores_updated=scores_updated,
        )
