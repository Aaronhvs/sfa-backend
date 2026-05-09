from __future__ import annotations

import pytest

from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
from sfa.domain.enrichment_ports import PlayerEnrichDTO
from sfa.domain.ingestion_ports import (
    FixtureEventRawDTO,
    IngestionRepositoryPort,
)
from sfa.domain.raw_data_ports import RawDataRepositoryPort, RawPlayerStatsDTO
from sfa.domain.scoring.services import SFAScoringService
from sfa.infrastructure.models.enums import EventType, IngestionStatus, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPETITION_ID = 1
_SEASON = "2024"

# Fixture events for a match where:
#   - Away team (1002) scored at minute 60  → score is 0-1 before minute 85
#   - Home player scored at minute 85        → M3 = 2.5 (losing ≤0, 80-90 window)
_AWAY_GOAL_EVT = FixtureEventRawDTO(
    type="Goal",
    detail="Normal Goal",
    player_name="Away Scorer",
    assist_name=None,
    team_external_id=1002,
    minute=60,
    extra_minute=0,
)

_HOME_GOAL_EVT = FixtureEventRawDTO(
    type="Goal",
    detail="Normal Goal",
    player_name="Test Player",
    assist_name=None,
    team_external_id=1001,
    minute=85,
    extra_minute=0,
)

_RAW_DTO_GOAL_85 = RawPlayerStatsDTO(
    player_id=42,
    fixture_id=9001,
    competition_id=_COMPETITION_ID,
    season=_SEASON,
    player_name="Test Player",
    position=Position.DEL,
    goals=1,
    assists=0,
    shots_on=2,
    passes_key=1,
    dribbles_success=0,
    duels_won=0,
    tackles=0,
    interceptions=0,
    blocks=0,
    minutes=90,
    is_away=False,
    rival_position=5,
    player_team_position=3,
    stage_factor=1.0,
    home_team_external_id=1001,
    fixture_events=[_AWAY_GOAL_EVT, _HOME_GOAL_EVT],
)

_RAW_DTO_SHORT_MINUTES = RawPlayerStatsDTO(
    player_id=99,
    fixture_id=9002,
    competition_id=_COMPETITION_ID,
    season=_SEASON,
    player_name="Short Player",
    position=Position.MC,
    goals=0,
    assists=0,
    shots_on=0,
    passes_key=0,
    dribbles_success=0,
    duels_won=3,
    tackles=1,
    interceptions=0,
    blocks=0,
    minutes=85,
    is_away=False,
    rival_position=5,
    player_team_position=3,
    stage_factor=1.0,
    home_team_external_id=1001,
    fixture_events=[],
)

_RAW_DTO_OTHER_PLAYER = RawPlayerStatsDTO(
    player_id=77,
    fixture_id=9003,
    competition_id=_COMPETITION_ID,
    season=_SEASON,
    player_name="Other Player",
    position=Position.LAT,
    goals=0,
    assists=0,
    shots_on=0,
    passes_key=0,
    dribbles_success=0,
    duels_won=2,
    tackles=2,
    interceptions=1,
    blocks=0,
    minutes=90,
    is_away=False,
    rival_position=5,
    player_team_position=3,
    stage_factor=1.0,
    home_team_external_id=1001,
    fixture_events=[],
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRawDataRepository(RawDataRepositoryPort):
    def __init__(self, raw_stats: list[RawPlayerStatsDTO] | None = None) -> None:
        self._raw_stats = raw_stats if raw_stats is not None else []

    async def get_raw_stats_for_calculation(
        self,
        competition_id: int,
        season: str,
        player_ids: list[int] | None = None,
    ) -> list[RawPlayerStatsDTO]:
        if player_ids is None:
            return self._raw_stats
        return [dto for dto in self._raw_stats if dto.player_id in player_ids]

    async def get_fixture_events_raw(self, fixture_id: int) -> list[FixtureEventRawDTO]:
        return []

    async def get_players_in_competition(
        self, competition_id: int, season: str,
    ) -> list[PlayerEnrichDTO]:
        return []

    async def get_downloaded_fixture_ids(
        self, competition_id: int, season: str,
    ) -> set[int]:
        return set()


class FakeIngestionRepository(IngestionRepositoryPort):
    def __init__(self) -> None:
        self.player_events: list[dict] = []
        self.season_scores: list[dict] = []

    async def upsert_competition(self, name: str, country: str, factor: float) -> int:
        return 1

    async def upsert_team(self, external_id: int, name: str, competition_id: int) -> int:
        return external_id

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
        photo_url: str | None = None,
    ) -> int:
        return external_id

    async def upsert_fixture(
        self, external_id: int, competition_id: int,
        home_team_id: int, away_team_id: int,
        stage: str, season: str, played_at: object, matchday: int | None,
    ) -> int:
        return external_id

    async def upsert_standing_snapshot(
        self, competition_id: int, team_id: int,
        season: str, matchday: int, position: int, points: int,
    ) -> None:
        pass

    async def upsert_player_event(
        self, player_id: int, fixture_id: int,
        minute: int, event_type: EventType,
        score_before: str | None, score_diff: int | None,
        psxg: float | None,
        m1: float, m2: float, m3: float, m4: float,
        mvisit: float, pts: float,
    ) -> None:
        self.player_events.append({
            "player_id": player_id,
            "fixture_id": fixture_id,
            "minute": minute,
            "event_type": event_type,
            "score_before": score_before,
            "score_diff": score_diff,
            "psxg": psxg,
            "m1": m1,
            "m2": m2,
            "m3": m3,
            "m4": m4,
            "mvisit": mvisit,
            "pts": pts,
        })

    async def upsert_player_stats(
        self, player_id: int, fixture_id: int, season: str, stats: dict,
    ) -> None:
        pass

    async def upsert_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float, matches_played: int, breakdown: dict,
    ) -> None:
        self.season_scores.append({"player_id": player_id, "total_pts": total_pts})

    async def get_stage_factor(self, competition_id: int, stage: str) -> float:
        return 1.0

    async def save_ingestion_log(
        self, competition_id: int, season: str,
        status: IngestionStatus, players_processed: int | None, error_msg: str | None,
    ) -> None:
        pass

    async def delete_player_events_for_fixture(
        self, player_id: int, fixture_id: int,
    ) -> None:
        pass

    async def fixture_players_already_downloaded(self, fixture_id: int) -> bool:
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalculateSFAFromRawUseCase:

    @pytest.mark.anyio
    async def test_goal_minute_85_losing_generates_m3_2_5(self):
        """A goal at minute 85 while losing (score 0-1) must produce M3=2.5."""
        raw_repo = FakeRawDataRepository(raw_stats=[_RAW_DTO_GOAL_85])
        ingestion_repo = FakeIngestionRepository()
        uc = CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, SFAScoringService())

        result = await uc.execute(_COMPETITION_ID, _SEASON)

        assert result.status == "completed"
        assert result.events_created >= 1

        goal_event = next(
            e for e in ingestion_repo.player_events if e["event_type"] == EventType.GOAL
        )
        assert goal_event["m3"] == 2.5
        assert goal_event["score_diff"] == -1
        assert goal_event["minute"] == 85

    @pytest.mark.anyio
    async def test_player_under_90_min_no_season_score(self):
        """A player with fewer than 90 total minutes must NOT get a season score."""
        raw_repo = FakeRawDataRepository(raw_stats=[_RAW_DTO_SHORT_MINUTES])
        ingestion_repo = FakeIngestionRepository()
        uc = CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, SFAScoringService())

        result = await uc.execute(_COMPETITION_ID, _SEASON)

        assert result.scores_updated == 0
        assert ingestion_repo.season_scores == []

    @pytest.mark.anyio
    async def test_player_ids_filter_limits_calculation(self):
        """Passing player_ids=[42] must only calculate events for player 42."""
        all_stats = [_RAW_DTO_GOAL_85, _RAW_DTO_OTHER_PLAYER]
        raw_repo = FakeRawDataRepository(raw_stats=all_stats)
        ingestion_repo = FakeIngestionRepository()
        uc = CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, SFAScoringService())

        result = await uc.execute(_COMPETITION_ID, _SEASON, player_ids=[42])

        assert result.players_calculated == 1
        player_ids_in_events = {e["player_id"] for e in ingestion_repo.player_events}
        assert player_ids_in_events <= {42}

    @pytest.mark.anyio
    async def test_player_over_90_min_gets_season_score(self):
        """A player with exactly 90 minutes must receive a season score."""
        raw_repo = FakeRawDataRepository(raw_stats=[_RAW_DTO_GOAL_85])
        ingestion_repo = FakeIngestionRepository()
        uc = CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, SFAScoringService())

        result = await uc.execute(_COMPETITION_ID, _SEASON)

        assert result.scores_updated == 1
        assert len(ingestion_repo.season_scores) == 1
        assert ingestion_repo.season_scores[0]["player_id"] == 42

    @pytest.mark.anyio
    async def test_empty_raw_stats_returns_completed_with_zeros(self):
        raw_repo = FakeRawDataRepository(raw_stats=[])
        ingestion_repo = FakeIngestionRepository()
        uc = CalculateSFAFromRawUseCase(raw_repo, ingestion_repo, SFAScoringService())

        result = await uc.execute(_COMPETITION_ID, _SEASON)

        assert result.status == "completed"
        assert result.players_calculated == 0
        assert result.events_created == 0
        assert result.scores_updated == 0
