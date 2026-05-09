import pytest

from sfa.application.use_cases.get_player_detail import (
    GetPlayerDetailUseCase,
    PlayerNotFoundError,
)
from sfa.domain.ports import PlayerScoreDTO, SFAScoreRepositoryProtocol


class FakeSFAScoreRepository(SFAScoreRepositoryProtocol):
    def __init__(
        self,
        best_score: PlayerScoreDTO | None = None,
        global_rank: int = 1,
        competitions: list[str] | None = None,
        latest_season: str | None = "2024-25",
        latest_season_for_player: str | None = "2024-25",
    ):
        self._best_score = best_score
        self._global_rank = global_rank
        self._competitions = competitions or []
        self._latest_season = latest_season
        self._latest_season_for_player = latest_season_for_player

    async def get_best_score_for_player_season(self, player_id, season):
        return self._best_score

    async def get_global_rank(self, player_id, season, total_pts):
        return self._global_rank

    async def get_competitions_for_player_season(self, player_id, season):
        return self._competitions

    async def get_ranking(self, season, position=None, competition_id=None, limit=50):
        return []

    async def get_ranking_total(self, season, position=None, competition_id=None):
        return 0

    async def latest_season(self):
        return self._latest_season

    async def latest_season_for_player(self, player_id):
        return self._latest_season_for_player


@pytest.fixture
def sample_score() -> PlayerScoreDTO:
    return PlayerScoreDTO(
        player_id=1,
        player_name="Messi",
        team_name="Inter Miami",
        position="DEL",
        competition_name="MLS",
        competition_id=10,
        total_pts=1500.0,
        matches_played=20,
        photo_url="https://example.com/messi.jpg",
        breakdown={"goal": {"count": 10, "pts": 500.0}},
    )


class TestGetPlayerDetail:
    @pytest.mark.anyio
    async def test_returns_detail_with_explicit_season(self, sample_score):
        repo = FakeSFAScoreRepository(
            best_score=sample_score,
            global_rank=3,
            competitions=["MLS", "Copa America"],
        )
        uc = GetPlayerDetailUseCase(repo)

        result = await uc.execute(player_id=1, season="2024-25")

        assert result.id == 1
        assert result.name == "Messi"
        assert result.global_rank == 3
        assert result.season == "2024-25"
        assert result.competitions == ["MLS", "Copa America"]

    @pytest.mark.anyio
    async def test_resolves_latest_season_when_none(self, sample_score):
        repo = FakeSFAScoreRepository(
            best_score=sample_score,
            latest_season_for_player="2023-24",
        )
        uc = GetPlayerDetailUseCase(repo)

        result = await uc.execute(player_id=1)

        assert result.season == "2023-24"

    @pytest.mark.anyio
    async def test_raises_when_player_not_found(self):
        repo = FakeSFAScoreRepository(
            best_score=None,
            latest_season_for_player="2024-25",
        )
        uc = GetPlayerDetailUseCase(repo)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(player_id=999, season="2024-25")

    @pytest.mark.anyio
    async def test_raises_when_no_season_found(self):
        repo = FakeSFAScoreRepository(latest_season_for_player=None)
        uc = GetPlayerDetailUseCase(repo)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(player_id=1)

    @pytest.mark.anyio
    async def test_fake_isinstance_protocol(self):
        repo = FakeSFAScoreRepository()
        assert isinstance(repo, SFAScoreRepositoryProtocol)

    @pytest.mark.anyio
    async def test_parses_breakdown(self, sample_score):
        repo = FakeSFAScoreRepository(best_score=sample_score)
        uc = GetPlayerDetailUseCase(repo)

        result = await uc.execute(player_id=1, season="2024-25")

        assert result.breakdown is not None
        assert "goal" in result.breakdown
        assert result.breakdown["goal"].count == 10
        assert result.breakdown["goal"].pts == 500.0
