import pytest

from sfa.application.use_cases.get_status import GetStatusUseCase, StatusResult
from sfa.domain.ports import SystemCountsDTO, SystemRepositoryProtocol


class FakeSystemRepository(SystemRepositoryProtocol):
    def __init__(self, counts: SystemCountsDTO | None = None):
        self._counts = counts or SystemCountsDTO(
            players=100,
            scores=500,
            competitions=5,
            events=2000,
            latest_season="2024-25",
        )

    async def get_counts(self) -> SystemCountsDTO:
        return self._counts


class TestGetStatus:
    @pytest.mark.anyio
    async def test_returns_correct_counts(self):
        counts = SystemCountsDTO(
            players=42,
            scores=210,
            competitions=3,
            events=800,
            latest_season="2024-25",
        )
        repo = FakeSystemRepository(counts=counts)
        uc = GetStatusUseCase(repo)

        result = await uc.execute()

        assert isinstance(result, StatusResult)
        assert result.players == 42
        assert result.scores == 210
        assert result.competitions == 3
        assert result.events == 800
        assert result.latest_season == "2024-25"

    @pytest.mark.anyio
    async def test_handles_no_season(self):
        counts = SystemCountsDTO(
            players=0,
            scores=0,
            competitions=0,
            events=0,
            latest_season=None,
        )
        repo = FakeSystemRepository(counts=counts)
        uc = GetStatusUseCase(repo)

        result = await uc.execute()

        assert result.latest_season is None

    @pytest.mark.anyio
    async def test_fake_isinstance_protocol(self):
        repo = FakeSystemRepository()
        assert isinstance(repo, SystemRepositoryProtocol)
