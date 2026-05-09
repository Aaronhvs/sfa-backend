import pytest

from sfa.application.use_cases.get_standings import GetStandingsUseCase, StandingsResult
from sfa.domain.ports import StandingEntryDTO, StandingRepositoryProtocol


class FakeStandingRepository(StandingRepositoryProtocol):
    def __init__(
        self,
        data: tuple[str, str, int, list[StandingEntryDTO]] | None = None,
        raise_error: str | None = None,
    ):
        self._data = data
        self._raise_error = raise_error

    async def get_standings(self, competition_id, season=None, matchday=None):
        if self._raise_error:
            raise ValueError(self._raise_error)
        if self._data is None:
            raise ValueError("No standings found")
        return self._data


def _make_entries() -> list[StandingEntryDTO]:
    return [
        StandingEntryDTO(position=1, team="Team A", points=30),
        StandingEntryDTO(position=2, team="Team B", points=25),
    ]


class TestGetStandings:
    @pytest.mark.anyio
    async def test_returns_standings(self):
        entries = _make_entries()
        repo = FakeStandingRepository(data=("Liga A", "2024-25", 10, entries))
        uc = GetStandingsUseCase(repo)

        result = await uc.execute(competition_id=1)

        assert isinstance(result, StandingsResult)
        assert result.competition == "Liga A"
        assert result.season == "2024-25"
        assert result.matchday == 10
        assert len(result.standings) == 2

    @pytest.mark.anyio
    async def test_raises_value_error_when_not_found(self):
        repo = FakeStandingRepository(raise_error="Competition not found")
        uc = GetStandingsUseCase(repo)

        with pytest.raises(ValueError, match="Competition not found"):
            await uc.execute(competition_id=999)

    @pytest.mark.anyio
    async def test_fake_isinstance_protocol(self):
        repo = FakeStandingRepository()
        assert isinstance(repo, StandingRepositoryProtocol)
