from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sfa.domain.ingestion_ports import (
    FixtureEventRawDTO,
    FootballDataProviderPort,
    IngestionRepositoryPort,
    LeagueConfigDTO,
)
from sfa.domain.position_mapping import map_position
from sfa.domain.scoring.services import BASE_POINTS_TABLE, SFAScoringService
from sfa.domain.scoring.value_objects import (
    ActionType,
    CombinedMultiplier,
    M1RivalDifficulty,
    M2CompetitionStage,
    M3MinuteScore,
    M4ShotDifficulty,
    MvisitFactor,
    SFAScore,
    position_to_group,
)
from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    competition: str
    players_processed: int
    fixtures_processed: int
    status: str
    error: str | None

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _PlayerAccum:
    total_pts: float = 0.0
    matches_played: int = 0
    total_minutes: int = 0
    breakdown: dict = field(default_factory=dict)


def _parse_matchday(round_str: str) -> int | None:
    m = re.search(r"(\d+)$", round_str)
    return int(m.group(1)) if m else None


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


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class IngestCompetitionUseCase:
    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._provider = provider
        self._repo = repo
        self._scoring = scoring

    async def execute(self, league: LeagueConfigDTO, season: int) -> IngestionResult:
        competition_id: int | None = None
        players_processed = 0
        fixtures_processed = 0
        player_accum: dict[int, _PlayerAccum] = {}
        season_str = str(season)

        try:
            # --- Phase 1: Standings ---
            standings = await self._provider.fetch_standings(league.external_id, season)
            if not standings:
                return IngestionResult(
                    competition=league.name,
                    players_processed=0,
                    fixtures_processed=0,
                    status="completed",
                    error=None,
                )

            competition_id = league.competition_id

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
                    team_ext_id, league.external_id, season
                )

                for fixture in fixtures:
                    if fixture.external_id in processed_fixture_ids:
                        continue
                    processed_fixture_ids.add(fixture.external_id)

                    stage = self._provider.get_stage(fixture.round_str, fixture.league_name)
                    stage_factor = await self._repo.get_stage_factor(competition_id, stage)
                    matchday_num = _parse_matchday(fixture.round_str)

                    # Ensure both teams exist in the DB
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

                    # --- Phase 3: Events and players ---
                    events = await self._provider.fetch_fixture_events(fixture.external_id)

                    for proc_team_ext_id in (
                        fixture.home_team_external_id,
                        fixture.away_team_external_id,
                    ):
                        player_stats_list = await self._provider.fetch_fixture_players(
                            fixture.external_id, proc_team_ext_id
                        )

                        rival_ext_id = (
                            fixture.away_team_external_id
                            if proc_team_ext_id == fixture.home_team_external_id
                            else fixture.home_team_external_id
                        )
                        player_team_pos = pos_cache.get(proc_team_ext_id, 10)
                        rival_pos = pos_cache.get(rival_ext_id, 10)
                        is_away = proc_team_ext_id == fixture.away_team_external_id
                        proc_team_db_id = team_id_map[proc_team_ext_id]

                        for ps in player_stats_list:
                            if ps.minutes < 20:
                                continue

                            position = map_position(ps.player_name, ps.position)
                            player_db_id = await self._repo.upsert_player(
                                ps.player_external_id, ps.player_name,
                                proc_team_db_id, position,
                            )

                            if player_db_id not in player_accum:
                                player_accum[player_db_id] = _PlayerAccum()
                            accum = player_accum[player_db_id]
                            accum.total_minutes += ps.minutes
                            accum.matches_played += 1

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
                                },
                            )

                            # GK: skip SFA event scoring
                            if position == Position.GK:
                                continue

                            group = position_to_group(position)

                            # Delete stale events for idempotency
                            await self._repo.delete_player_events_for_fixture(
                                player_db_id, fixture_db_id
                            )

                            # Goals
                            player_goals = [
                                e for e in events
                                if e.type == "Goal"
                                and e.detail not in ("Missed Penalty", "Own Goal")
                                and _name_matches(e.player_name, ps.player_name)
                                and e.team_external_id == proc_team_ext_id
                            ]
                            for goal_evt in player_goals:
                                await self._process_event(
                                    accum=accum,
                                    evt=goal_evt,
                                    all_events=events,
                                    player_db_id=player_db_id,
                                    fixture_db_id=fixture_db_id,
                                    group=group,
                                    player_team_pos=player_team_pos,
                                    rival_pos=rival_pos,
                                    stage_factor=stage_factor,
                                    is_away=is_away,
                                    home_team_ext_id=fixture.home_team_external_id,
                                    is_assist=False,
                                )

                            # Assists
                            player_assists = [
                                e for e in events
                                if e.type == "Goal"
                                and e.detail not in ("Missed Penalty", "Own Goal")
                                and e.assist_name is not None
                                and _name_matches(e.assist_name, ps.player_name)
                                and e.team_external_id == proc_team_ext_id
                            ]
                            for assist_evt in player_assists:
                                await self._process_event(
                                    accum=accum,
                                    evt=assist_evt,
                                    all_events=events,
                                    player_db_id=player_db_id,
                                    fixture_db_id=fixture_db_id,
                                    group=group,
                                    player_team_pos=player_team_pos,
                                    rival_pos=rival_pos,
                                    stage_factor=stage_factor,
                                    is_away=is_away,
                                    home_team_ext_id=fixture.home_team_external_id,
                                    is_assist=True,
                                )

                            # Match stats
                            stats_for_scoring = {
                                ActionType.DUELS_WON: ps.duels_won,
                                ActionType.TACKLES_INTERCEPTIONS: ps.tackles + ps.interceptions,
                                ActionType.BLOCKS: ps.blocks,
                                ActionType.DRIBBLES_WON: ps.dribbles_success,
                            }
                            stat_scores = self._scoring.score_match_stats(
                                group, stats_for_scoring,
                                player_team_pos, rival_pos, stage_factor,
                            )
                            for s in stat_scores:
                                accum.total_pts += s.total
                                _add_to_breakdown(accum.breakdown, "stats", s.total)

                    fixtures_processed += 1

            # --- Phase 4: Season scores ---
            for player_db_id, accum in player_accum.items():
                if accum.total_minutes < 90:
                    continue

                total = accum.total_pts
                for key in accum.breakdown:
                    pct = (
                        round(accum.breakdown[key]["pts"] / total * 100, 1)
                        if total > 0 else 0.0
                    )
                    accum.breakdown[key]["pct"] = pct

                await self._repo.upsert_season_score(
                    player_db_id, competition_id, season_str,
                    round(accum.total_pts, 2),
                    accum.matches_played,
                    accum.breakdown,
                )
                players_processed += 1

            # --- Phase 5: Log ---
            await self._repo.save_ingestion_log(
                competition_id, season_str,
                IngestionStatus.COMPLETED, players_processed, None,
            )

            return IngestionResult(
                competition=league.name,
                players_processed=players_processed,
                fixtures_processed=fixtures_processed,
                status="completed",
                error=None,
            )

        except Exception as exc:
            logger.exception(
                "Ingestion failed for %s season %s", league.name, season
            )
            if competition_id is not None:
                try:
                    await self._repo.save_ingestion_log(
                        competition_id, season_str,
                        IngestionStatus.FAILED, players_processed, str(exc),
                    )
                except Exception:
                    pass
            return IngestionResult(
                competition=league.name,
                players_processed=players_processed,
                fixtures_processed=fixtures_processed,
                status="failed",
                error=str(exc),
            )

    async def _process_event(
        self,
        *,
        accum: _PlayerAccum,
        evt: FixtureEventRawDTO,
        all_events: list[FixtureEventRawDTO],
        player_db_id: int,
        fixture_db_id: int,
        group: object,
        player_team_pos: int,
        rival_pos: int,
        stage_factor: float,
        is_away: bool,
        home_team_ext_id: int,
        is_assist: bool,
    ) -> None:
        minute = evt.minute + evt.extra_minute
        clamped = max(1, min(90, minute))
        is_penalty = evt.detail == "Penalty"

        home_b, away_b = self._provider.get_score_at_minute(
            all_events, minute, home_team_ext_id
        )
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
            return

        m1 = M1RivalDifficulty(player_team_pos, rival_pos)
        m2 = M2CompetitionStage(stage_factor)
        m3 = M3MinuteScore(clamped, score_diff, is_penalty)
        m4 = M4ShotDifficulty(psxg)
        mvisit = MvisitFactor(is_away, True)
        combined = CombinedMultiplier(m1, m2, m3, m4, mvisit)
        sfa = SFAScore(base_pts, combined)

        await self._repo.upsert_player_event(
            player_db_id, fixture_db_id,
            minute, event_type,
            score_before_str, score_diff, psxg,
            m1.value, m2.value, m3.value, m4.value, mvisit.value,
            round(sfa.total, 2),
        )

        _add_to_breakdown(accum.breakdown, action.value, sfa.total)
        accum.total_pts += sfa.total
