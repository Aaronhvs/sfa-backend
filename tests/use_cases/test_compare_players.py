import pytest

from sfa.application.use_cases.compare_players import ComparePlayersUseCase
from sfa.application.use_cases.get_player_detail import PlayerNotFoundError
from sfa.domain.ports import PlayerScoreDTO, SFAScoreRepositoryProtocol


def _make_score(player_id: int, name: str) -> PlayerScoreDTO:
    return PlayerScoreDTO(
        player_id=player_id,
        player_name=name,
        team_name="Team A",
        position="DEL",
        competition_name="Liga",
        competition_id=1,
        total_pts=1000.0,
        matches_played=20,
        photo_url=None,
        breakdown=None,
    )


class FakeSFAScoreRepository(SFAScoreRepositoryProtocol):
    def __init__(self, scores: dict[int, PlayerScoreDTO], season: str = "2024-25"):
        self._scores = scores
        self._season = season

    async def get_best_score_for_player_season(self, player_id, season):
        return self._scores.get(player_id)

    async def get_global_rank(self, player_id, season, total_pts):
        return 1

    async def get_competitions_for_player_season(self, player_id, season):
        return ["Liga"]

    async def get_ranking(self, season, position=None, competition_id=None, limit=50):
        return []

    async def get_ranking_total(self, season, position=None, competition_id=None):
        return 0

    async def latest_season(self):
        return self._season

    async def latest_season_for_player(self, player_id):
        if player_id in self._scores:
            return self._season
        return None


class TestComparePlayers:
    @pytest.mark.anyio
    async def test_compare_two_players(self):
        score_a = _make_score(1, "Messi")
        score_b = _make_score(2, "Ronaldo")
        repo = FakeSFAScoreRepository(scores={1: score_a, 2: score_b})
        uc = ComparePlayersUseCase(repo)

        result = await uc.execute(player_a_id=1, player_b_id=2, season="2024-25")

        assert result.player_a.name == "Messi"
        assert result.player_b.name == "Ronaldo"
        assert result.season == "2024-25"

    @pytest.mark.anyio
    async def test_raises_when_player_a_not_found(self):
        score_b = _make_score(2, "Ronaldo")
        repo = FakeSFAScoreRepository(scores={2: score_b})
        uc = ComparePlayersUseCase(repo)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(player_a_id=999, player_b_id=2, season="2024-25")

    @pytest.mark.anyio
    async def test_raises_when_player_b_not_found(self):
        score_a = _make_score(1, "Messi")
        repo = FakeSFAScoreRepository(scores={1: score_a})
        uc = ComparePlayersUseCase(repo)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(player_a_id=1, player_b_id=999, season="2024-25")

    @pytest.mark.anyio
    async def test_resolves_season_from_player_a(self):
        score_a = _make_score(1, "Messi")
        score_b = _make_score(2, "Ronaldo")
        repo = FakeSFAScoreRepository(scores={1: score_a, 2: score_b}, season="2023-24")
        uc = ComparePlayersUseCase(repo)

        result = await uc.execute(player_a_id=1, player_b_id=2)

        assert result.season == "2023-24"
