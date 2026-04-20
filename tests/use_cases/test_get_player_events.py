from datetime import datetime

import pytest

from sfa.application.use_cases.get_player_events import GetPlayerEventsUseCase
from sfa.domain.ports import PlayerEventDTO, PlayerEventRepositoryProtocol, PlayerFixtureDTO


class FakePlayerEventRepository(PlayerEventRepositoryProtocol):
    def __init__(self, events: list[PlayerEventDTO] | None = None):
        self._events = events or []

    async def get_events_by_player(self, player_id, season=None, competition_id=None):
        return self._events

    async def get_fixtures_by_player(self, player_id, season=None, competition_id=None):
        return []


def _make_event() -> PlayerEventDTO:
    return PlayerEventDTO(
        id=1,
        competition="Liga",
        stage="Regular",
        fixture_id=100,
        home_team="Team A",
        away_team="Team B",
        played_at=datetime(2024, 10, 1, 15, 0),
        minute=30,
        event_type="goal",
        score_before="0-0",
        score_diff=1,
        m1=1.0,
        m2=0.5,
        m3=0.3,
        m4=0.2,
        mvisit=0.0,
        pts=50.0,
    )


class TestGetPlayerEvents:
    @pytest.mark.anyio
    async def test_returns_events(self):
        event = _make_event()
        repo = FakePlayerEventRepository(events=[event])
        uc = GetPlayerEventsUseCase(repo)

        result = await uc.execute(player_id=1)

        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].event_type == "goal"

    @pytest.mark.anyio
    async def test_returns_empty_list(self):
        repo = FakePlayerEventRepository(events=[])
        uc = GetPlayerEventsUseCase(repo)

        result = await uc.execute(player_id=99)

        assert result == []

    @pytest.mark.anyio
    async def test_passes_filters(self):
        calls = []

        class TrackingRepo(PlayerEventRepositoryProtocol):
            async def get_events_by_player(self, player_id, season=None, competition_id=None):
                calls.append((player_id, season, competition_id))
                return []

            async def get_fixtures_by_player(self, player_id, season=None, competition_id=None):
                return []

        uc = GetPlayerEventsUseCase(TrackingRepo())
        await uc.execute(player_id=5, season="2024-25", competition_id=3)

        assert calls == [(5, "2024-25", 3)]

    @pytest.mark.anyio
    async def test_fake_isinstance_protocol(self):
        repo = FakePlayerEventRepository()
        assert isinstance(repo, PlayerEventRepositoryProtocol)
