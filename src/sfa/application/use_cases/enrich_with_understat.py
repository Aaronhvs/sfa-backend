from __future__ import annotations

import logging

from sfa.domain.enrichment_ports import (
    EnrichmentRepositoryPort,
    EnrichmentResult,
    UnderstatProviderPort,
)
from sfa.domain.name_matching import find_best_match

logger = logging.getLogger(__name__)

_MIN_MINUTES = 90


class EnrichWithUnderstatUseCase:
    def __init__(
        self,
        understat: UnderstatProviderPort,
        repo: EnrichmentRepositoryPort,
    ) -> None:
        self._understat = understat
        self._repo = repo

    async def execute(
        self,
        competition_name: str,
        competition_id: int,
        season: str,
        season_int: int,
    ) -> EnrichmentResult:
        events_enriched = 0
        players_matched = 0
        players_skipped = 0

        # 7.1 — Champions League not available on Understat
        if competition_name == "Champions League":
            logger.info("Understat enrichment skipped: Champions League not available")
            return EnrichmentResult(
                competition=competition_name,
                players_matched=0,
                players_skipped=0,
                events_enriched=0,
                stats_enriched=0,
                status="completed",
                error=None,
            )

        try:
            # 7.2 — Fetch Understat players
            raw_players = await self._understat.fetch_league_players(
                competition_name, season_int
            )
            # Filter out players with too few minutes
            players = [p for p in raw_players if p.minutes >= _MIN_MINUTES]

            if not players:
                logger.warning(
                    "Understat returned no qualifying players for %s/%s",
                    competition_name, season_int,
                )
                return EnrichmentResult(
                    competition=competition_name,
                    players_matched=0,
                    players_skipped=0,
                    events_enriched=0,
                    stats_enriched=0,
                    status="completed",
                    error=None,
                )

            # 7.3 — Build DB index
            db_players = await self._repo.get_players_by_competition(
                competition_id, season
            )
            db_index: dict[str, object] = {p.name: p for p in db_players}

            # 7.4 — Match and enrich PSxG fallback
            for dto in players:
                player, score = find_best_match(dto.player_name, db_index)

                if player is None:
                    players_skipped += 1
                    continue

                players_matched += 1

                # Save understat_id
                await self._repo.update_player_external_ids(
                    player.id,
                    fbref_id=None,
                    understat_id=int(dto.understat_id),
                )

                # Only enrich PSxG where FBref has not already covered it
                events = await self._repo.get_player_events_without_psxg(
                    player.id, competition_id, season
                )
                if not events:
                    # FBref already covered this player
                    continue

                for event in events:
                    await self._repo.update_event_psxg(event.id, dto.xg_per_shot)
                    events_enriched += 1

            logger.info(
                "Understat enrichment for %s/%s: matched=%d skipped=%d events_enriched=%d",
                competition_name, season_int, players_matched, players_skipped, events_enriched,
            )

            return EnrichmentResult(
                competition=competition_name,
                players_matched=players_matched,
                players_skipped=players_skipped,
                events_enriched=events_enriched,
                stats_enriched=0,
                status="completed",
                error=None,
            )

        except Exception as exc:
            logger.exception(
                "Understat enrichment failed for %s", competition_name
            )
            return EnrichmentResult(
                competition=competition_name,
                players_matched=players_matched,
                players_skipped=players_skipped,
                events_enriched=events_enriched,
                stats_enriched=0,
                status="failed",
                error=str(exc),
            )
