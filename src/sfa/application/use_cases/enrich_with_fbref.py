from __future__ import annotations

import logging

from sfa.domain.enrichment_ports import (
    EnrichmentRepositoryPort,
    EnrichmentResult,
    FBrefProviderPort,
)
from sfa.domain.name_matching import find_best_match

logger = logging.getLogger(__name__)


class EnrichWithFBrefUseCase:
    def __init__(
        self,
        fbref: FBrefProviderPort,
        repo: EnrichmentRepositoryPort,
    ) -> None:
        self._fbref = fbref
        self._repo = repo

    async def execute(
        self,
        competition_name: str,
        competition_id: int,
        season: str,
    ) -> EnrichmentResult:
        players_matched = 0
        players_skipped = 0
        events_enriched = 0
        stats_enriched = 0

        try:
            # 6.1 — Fetch FBref stats
            fbref_players = await self._fbref.fetch_league_player_stats(competition_name)
            if not fbref_players:
                logger.warning(
                    "FBref returned no players for %s", competition_name
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

            # 6.2 — Build DB index {player_name: PlayerEnrichDTO}
            db_players = await self._repo.get_players_by_competition(
                competition_id, season
            )
            db_index: dict[str, object] = {p.name: p for p in db_players}

            if not db_index:
                logger.warning(
                    "No players found in DB for competition_id=%s season=%s",
                    competition_id, season,
                )
                return EnrichmentResult(
                    competition=competition_name,
                    players_matched=0,
                    players_skipped=len(fbref_players),
                    events_enriched=0,
                    stats_enriched=0,
                    status="completed",
                    error=None,
                )

            # 6.3 — Match and enrich
            for dto in fbref_players:
                player, score = find_best_match(dto.player_name, db_index)

                if player is None:
                    players_skipped += 1
                    if score == 0.0:
                        logger.debug("FBref no match: %s", dto.player_name)
                    else:
                        logger.warning(
                            "FBref ambiguous match: %s (score=%.2f)", dto.player_name, score
                        )
                    continue

                players_matched += 1

                # Save fbref_id (player name as cross-reference key)
                await self._repo.update_player_external_ids(
                    player.id, fbref_id=dto.player_name, understat_id=None
                )

                # Enrich player_stats with FBref season totals
                stats_to_update = {
                    "xg": dto.xg,
                    "xa": dto.xa,
                    "progressive_passes": dto.progressive_passes,
                    "progressive_carries": dto.progressive_carries,
                }
                await self._repo.update_player_stats_from_fbref(
                    player.id, season, stats_to_update
                )
                stats_enriched += 1

                # Enrich PSxG on goal events
                if dto.psxg_total is None or dto.goals == 0:
                    continue

                psxg_proxy = dto.psxg_total / dto.goals
                events = await self._repo.get_player_events_without_psxg(
                    player.id, competition_id, season
                )
                for event in events:
                    await self._repo.update_event_psxg(event.id, psxg_proxy)
                    events_enriched += 1

            logger.info(
                "FBref enrichment for %s: matched=%d skipped=%d "
                "events_enriched=%d stats_enriched=%d",
                competition_name, players_matched, players_skipped,
                events_enriched, stats_enriched,
            )

            return EnrichmentResult(
                competition=competition_name,
                players_matched=players_matched,
                players_skipped=players_skipped,
                events_enriched=events_enriched,
                stats_enriched=stats_enriched,
                status="completed",
                error=None,
            )

        except Exception as exc:
            logger.exception("FBref enrichment failed for %s", competition_name)
            return EnrichmentResult(
                competition=competition_name,
                players_matched=players_matched,
                players_skipped=players_skipped,
                events_enriched=events_enriched,
                stats_enriched=stats_enriched,
                status="failed",
                error=str(exc),
            )
