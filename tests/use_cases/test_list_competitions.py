import pytest

from sfa.application.use_cases.list_competitions import ListCompetitionsUseCase
from sfa.domain.ports import CompetitionDTO, CompetitionRepositoryProtocol


class FakeCompetitionRepository(CompetitionRepositoryProtocol):
    def __init__(self, competitions: list[CompetitionDTO] | None = None):
        self._competitions = competitions or []

    async def get_all(self) -> list[CompetitionDTO]:
        return self._competitions

    async def get_by_id(self, competition_id: int) -> CompetitionDTO | None:
        return next((c for c in self._competitions if c.id == competition_id), None)


def _make_competition(id: int, name: str) -> CompetitionDTO:
    return CompetitionDTO(id=id, name=name, country="AR", factor=1.0)


class TestListCompetitions:
    @pytest.mark.anyio
    async def test_returns_competitions(self):
        comps = [_make_competition(1, "Liga A"), _make_competition(2, "Copa B")]
        repo = FakeCompetitionRepository(competitions=comps)
        uc = ListCompetitionsUseCase(repo)

        result = await uc.execute()

        assert len(result) == 2
        assert result[0].name == "Liga A"

    @pytest.mark.anyio
    async def test_returns_empty_list(self):
        repo = FakeCompetitionRepository(competitions=[])
        uc = ListCompetitionsUseCase(repo)

        result = await uc.execute()

        assert result == []

    @pytest.mark.anyio
    async def test_fake_isinstance_protocol(self):
        repo = FakeCompetitionRepository()
        assert isinstance(repo, CompetitionRepositoryProtocol)
