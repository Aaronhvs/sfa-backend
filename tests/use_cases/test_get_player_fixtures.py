from datetime import datetime

import pytest

from sfa.application.use_cases.get_player_fixtures import GetPlayerFixturesUseCase
from sfa.domain.ports import PlayerEventRepositoryProtocol, PlayerFixtureDTO


class FakePlayerEventRepository(PlayerEventRepositoryProtocol):
    def __init__(self, fixtures: list[PlayerFixtureDTO] | None = None):
        self._fixtures = fixtures or []

    async def get_events_by_player(self, player_id, season=None, competition_id=None):
        return []

    async def get_fixtures_by_player(self, player_id, season=None, competition_id=None):
        return self._fixtures


def _make_fixture() -> PlayerFixtureDTO:
    return PlayerFixtureDTO(
        fixture_id=1,
        competition="Liga",
        stage="Regular",
        home_team="Team A",
        away_team="Team B",
        played_at=datetime(2024, 10, 1, 15, 0),
        sfa_pts=75.0,
        events_count=3,
    )


class TestGetPlayerFixtures:
    @pytest.mark.anyio
    async def test_returns_fixtures(self):
        fixture = _make_fixture()
        repo = FakePlayerEventRepository(fixtures=[fixture])
        uc = GetPlayerFixturesUseCase(repo)

        result = await uc.execute(player_id=1)

        assert len(result) == 1
        assert result[0].fixture_id == 1
        assert result[0].sfa_pts == 75.0

    @pytest.mark.anyio
    async def test_returns_empty_list(self):
        repo = FakePlayerEventRepository(fixtures=[])
        uc = GetPlayerFixturesUseCase(repo)

        result = await uc.execute(player_id=99)

        assert result == []

    @pytest.mark.anyio
    async def test_passes_filters(self):
        calls = []

        class TrackingRepo(PlayerEventRepositoryProtocol):
            async def get_events_by_player(self, player_id, season=None, competition_id=None):
                return []

            async def get_fixtures_by_player(self, player_id, season=None, competition_id=None):
                calls.append((player_id, season, competition_id))
                return []

        uc = GetPlayerFixturesUseCase(TrackingRepo())
        await uc.execute(player_id=7, season="2024-25", competition_id=2)

        assert calls == [(7, "2024-25", 2)]
