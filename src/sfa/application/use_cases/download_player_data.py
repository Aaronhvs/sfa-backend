from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sfa.domain.ingestion_ports import (
    DownloadResult,
    FootballDataProviderPort,
    IngestionRepositoryPort,
    LeagueConfig,
)
from sfa.domain.position_mapping import map_position
from sfa.infrastructure.models.enums import IngestionStatus

logger = logging.getLogger(__name__)


def _parse_matchday(round_str: str) -> int | None:
    m = re.search(r"(\d+)$", round_str)
    return int(m.group(1)) if m else None


@dataclass
class _FixtureAccum:
    downloaded: int = 0
    skipped: int = 0
    players: int = 0
    requests: int = 0


class DownloadPlayerDataUseCase:
    """Downloads raw player data from the API and persists it in player_stats.

    Responsibilities:
    - Fetch standings, fixtures, events and player stats from FootballDataProviderPort
    - Skip fixtures already present in the DB (idempotent)
    - Apply optional player name filter
    - Store photo_url on both Player and PlayerStats

    NOT responsible for:
    - SFA scoring (no player_events, no sfa_season_scores)
    """

    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
    ) -> None:
        self._provider = provider
        self._repo = repo

    async def execute(
        self,
        league: LeagueConfig,
        season: int,
        player_filter: list[str] | None = None,
    ) -> DownloadResult:
        acc = _FixtureAccum()
        season_str = str(season)
        competition_id: int | None = None

        try:
            # --- Phase 1: Standings ---
            standings = await self._provider.fetch_standings(league.id, season)
            acc.requests += 1

            if not standings:
                return DownloadResult(
                    competition=league.name,
                    fixtures_downloaded=0,
                    fixtures_skipped=0,
                    players_downloaded=0,
                    requests_used=acc.requests,
                    status="completed",
                    error=None,
                )

            competition_id = await self._repo.upsert_competition(
                league.name, league.country, league.comp_factor
            )

            matchday = max((s.played for s in standings), default=0)
            pos_cache: dict[int, int] = {}
            team_id_map: dict[int, int] = {}

            for standing in standings:
                team_db_id = await self._repo.upsert_team(
                    standing.team_external_id, standing.team_name, competition_id
                )
                team_id_map[standing.team_external_id] = team_db_id
                pos_cache[standing.team_external_id] = standing.position

                if matchday > 0:
                    await self._repo.upsert_standing_snapshot(
                        competition_id, team_db_id, season_str,
                        matchday, standing.position, standing.points,
                    )

            # --- Phase 2: Fixtures per top_n teams ---
            top_teams = sorted(standings, key=lambda s: s.position)[: league.top_n]
            processed_fixture_ids: set[int] = set()

            for team_standing in top_teams:
                team_ext_id = team_standing.team_external_id
                fixtures = await self._provider.fetch_team_fixtures(
                    team_ext_id, league.id, season
                )
                acc.requests += 1

                for fixture in fixtures:
                    if fixture.external_id in processed_fixture_ids:
                        continue
                    processed_fixture_ids.add(fixture.external_id)

                    stage = self._provider.get_stage(fixture.round_str, fixture.league_name)
                    matchday_num = _parse_matchday(fixture.round_str)

                    for ext_id, name in [
                        (fixture.home_team_external_id, fixture.home_team_name),
                        (fixture.away_team_external_id, fixture.away_team_name),
                    ]:
                        if ext_id not in team_id_map:
                            db_id = await self._repo.upsert_team(ext_id, name, competition_id)
                            team_id_map[ext_id] = db_id
                            if ext_id not in pos_cache:
                                pos_cache[ext_id] = 10

                    home_db_id = team_id_map[fixture.home_team_external_id]
                    away_db_id = team_id_map[fixture.away_team_external_id]

                    fixture_db_id = await self._repo.upsert_fixture(
                        fixture.external_id, competition_id,
                        home_db_id, away_db_id,
                        stage, season_str, fixture.played_at, matchday_num,
                    )

                    # --- Skip if data already downloaded ---
                    if await self._repo.fixture_players_already_downloaded(fixture_db_id):
                        acc.skipped += 1
                        logger.debug(
                            "[DownloadPlayerDataUseCase] Skipping fixture %d (already downloaded)",
                            fixture.external_id,
                        )
                        continue

                    # --- Phase 3: Events and player stats ---
                    await self._provider.fetch_fixture_events(fixture.external_id)
                    acc.requests += 1
                    all_fixture_players = await self._provider.fetch_fixture_players(
                        fixture.external_id
                    )
                    acc.requests += 1

                    for proc_team_ext_id in (
                        fixture.home_team_external_id,
                        fixture.away_team_external_id,
                    ):
                        player_stats_list = all_fixture_players.get(proc_team_ext_id, [])
                        proc_team_db_id = team_id_map[proc_team_ext_id]

                        for ps in player_stats_list:
                            if ps.minutes < 20:
                                continue

                            if player_filter is not None:
                                if not any(
                                    f.lower() in ps.player_name.lower()
                                    for f in player_filter
                                ):
                                    continue

                            position = map_position(ps.player_name, ps.position)
                            player_db_id = await self._repo.upsert_player(
                                ps.player_external_id, ps.player_name,
                                proc_team_db_id, position,
                                photo_url=ps.photo_url,
                            )

                            await self._repo.upsert_player_stats(
                                player_db_id, fixture_db_id, season_str,
                                {
                                    "goals": ps.goals,
                                    "assists": ps.assists,
                                    "shots_on": ps.shots_on,
                                    "passes_key": ps.passes_key,
                                    "dribbles_won": ps.dribbles_success,
                                    "duels_won": ps.duels_won,
                                    "tackles_won": ps.tackles,
                                    "interceptions": ps.interceptions,
                                    "blocks": ps.blocks,
                                    "minutes": ps.minutes,
                                    "photo_url": ps.photo_url,
                                },
                            )
                            acc.players += 1

                    acc.downloaded += 1

            await self._repo.save_ingestion_log(
                competition_id, season_str,
                IngestionStatus.COMPLETED, acc.players, None,
            )

            return DownloadResult(
                competition=league.name,
                fixtures_downloaded=acc.downloaded,
                fixtures_skipped=acc.skipped,
                players_downloaded=acc.players,
                requests_used=acc.requests,
                status="completed",
                error=None,
            )

        except Exception as exc:
            logger.exception(
                "[DownloadPlayerDataUseCase] Failed for %s season %s",
                league.name, season,
            )
            if competition_id is not None:
                try:
                    await self._repo.save_ingestion_log(
                        competition_id, season_str,
                        IngestionStatus.FAILED, acc.players, str(exc),
                    )
                except Exception:
                    pass
            return DownloadResult(
                competition=league.name,
                fixtures_downloaded=acc.downloaded,
                fixtures_skipped=acc.skipped,
                players_downloaded=acc.players,
                requests_used=acc.requests,
                status="failed",
                error=str(exc),
            )
