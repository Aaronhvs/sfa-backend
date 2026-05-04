import pytest

from sfa.application.use_cases.get_ranking import GetRankingUseCase, RankingResult
from sfa.domain.ports import RankedPlayerDTO, SFAScoreRepositoryProtocol


class FakeSFAScoreRepository(SFAScoreRepositoryProtocol):
    def __init__(
        self,
        ranking: list[RankedPlayerDTO] | None = None,
        total: int = 0,
        season: str | None = "2024-25",
    ):
        self._ranking = ranking or []
        self._total = total
        self._season = season

    async def get_best_score_for_player_season(self, player_id, season):
        return None

    async def get_global_rank(self, player_id, season, total_pts):
        return 1

    async def get_competitions_for_player_season(self, player_id, season):
        return []

    async def get_ranking(self, season, position=None, competition_id=None, limit=50):
        return self._ranking

    async def get_ranking_total(self, season, position=None, competition_id=None):
        return self._total

    async def latest_season(self):
        return self._season

    async def latest_season_for_player(self, player_id):
        return self._season


def _make_ranked_player(rank: int = 1) -> RankedPlayerDTO:
    return RankedPlayerDTO(
        rank=rank,
        player_id=rank,
        player_name=f"Player {rank}",
        team_name="Team A",
        position="DEL",
        competition_name="Liga",
        total_pts=float(1000 - rank * 10),
        matches_played=20,
        photo_url=None,
    )


class TestGetRanking:
    @pytest.mark.anyio
    async def test_returns_ranking_with_season(self):
        players = [_make_ranked_player(1), _make_ranked_player(2)]
        repo = FakeSFAScoreRepository(ranking=players, total=2, season="2024-25")
        uc = GetRankingUseCase(repo)

        result = await uc.execute(season="2024-25")

        assert result.season == "2024-25"
        assert result.total == 2
        assert len(result.ranking) == 2

    @pytest.mark.anyio
    async def test_resolves_latest_season(self):
        repo = FakeSFAScoreRepository(season="2023-24", total=1, ranking=[_make_ranked_player()])
        uc = GetRankingUseCase(repo)

        result = await uc.execute()

        assert result.season == "2023-24"

    @pytest.mark.anyio
    async def test_returns_empty_when_no_season(self):
        repo = FakeSFAScoreRepository(season=None)
        uc = GetRankingUseCase(repo)

        result = await uc.execute()

        assert result.season == ""
        assert result.total == 0
        assert result.ranking == []

    @pytest.mark.anyio
    async def test_result_is_ranking_result(self):
        repo = FakeSFAScoreRepository()
        uc = GetRankingUseCase(repo)

        result = await uc.execute(season="2024-25")

        assert isinstance(result, RankingResult)
