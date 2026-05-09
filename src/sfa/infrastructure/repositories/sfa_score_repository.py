from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import (
    PlayerScoreDTO,
    RankedPlayerDTO,
    SFAScoreRepositoryProtocol,
)
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore
from sfa.infrastructure.models.teams.models import Team


class SFAScoreRepository(SFAScoreRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_best_score_for_player_season(
        self, player_id: int, season: str,
    ) -> PlayerScoreDTO | None:
        stmt = (
            select(
                Player.id.label("player_id"),
                Player.name.label("player_name"),
                Team.name.label("team_name"),
                Player.position,
                Competition.name.label("competition_name"),
                SFASeasonScore.competition_id,
                SFASeasonScore.total_pts,
                SFASeasonScore.matches_played,
                Player.photo_url,
                SFASeasonScore.breakdown,
            )
            .join(Player, SFASeasonScore.player_id == Player.id)
            .join(Team, Player.team_id == Team.id)
            .join(Competition, SFASeasonScore.competition_id == Competition.id)
            .where(SFASeasonScore.player_id == player_id)
            .where(SFASeasonScore.season == season)
            .order_by(SFASeasonScore.total_pts.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None
        return PlayerScoreDTO(
            player_id=row["player_id"],
            player_name=row["player_name"],
            team_name=row["team_name"],
            position=row["position"].value,
            competition_name=row["competition_name"],
            competition_id=row["competition_id"],
            total_pts=float(row["total_pts"]),
            matches_played=row["matches_played"],
            photo_url=row["photo_url"],
            breakdown=row["breakdown"],
        )

    async def get_global_rank(
        self, player_id: int, season: str, total_pts: float,
    ) -> int:
        stmt = select(func.count()).where(
            SFASeasonScore.player_id != player_id,
            SFASeasonScore.season == season,
            SFASeasonScore.total_pts > total_pts,
        )
        return (await self._session.execute(stmt)).scalar_one() + 1

    async def get_competitions_for_player_season(
        self, player_id: int, season: str,
    ) -> list[str]:
        stmt = (
            select(Competition.name)
            .join(SFASeasonScore, SFASeasonScore.competition_id == Competition.id)
            .where(
                SFASeasonScore.player_id == player_id,
                SFASeasonScore.season == season,
            )
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_ranking(
        self,
        season: str,
        position: str | None = None,
        competition_id: int | None = None,
        limit: int = 50,
    ) -> list[RankedPlayerDTO]:
        rank_col = func.rank().over(order_by=SFASeasonScore.total_pts.desc()).label("rank")
        stmt = (
            select(
                rank_col,
                Player.id.label("player_id"),
                Player.name.label("player_name"),
                Team.name.label("team_name"),
                Player.position,
                Competition.name.label("competition_name"),
                SFASeasonScore.total_pts,
                SFASeasonScore.matches_played,
                Player.photo_url,
            )
            .join(Player, SFASeasonScore.player_id == Player.id)
            .join(Team, Player.team_id == Team.id)
            .join(Competition, SFASeasonScore.competition_id == Competition.id)
            .where(SFASeasonScore.season == season)
            .order_by(SFASeasonScore.total_pts.desc())
            .limit(limit)
        )
        if position is not None:
            stmt = stmt.where(Player.position == position)
        if competition_id is not None:
            stmt = stmt.where(SFASeasonScore.competition_id == competition_id)

        rows = (await self._session.execute(stmt)).mappings().all()
        return [
            RankedPlayerDTO(
                rank=row["rank"],
                player_id=row["player_id"],
                player_name=row["player_name"],
                team_name=row["team_name"],
                position=row["position"].value,
                competition_name=row["competition_name"],
                total_pts=float(row["total_pts"]),
                matches_played=row["matches_played"],
                photo_url=row["photo_url"],
            )
            for row in rows
        ]

    async def get_ranking_total(
        self,
        season: str,
        position: str | None = None,
        competition_id: int | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(SFASeasonScore)
            .join(Player, SFASeasonScore.player_id == Player.id)
            .where(SFASeasonScore.season == season)
        )
        if position is not None:
            stmt = stmt.where(Player.position == position)
        if competition_id is not None:
            stmt = stmt.where(SFASeasonScore.competition_id == competition_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def latest_season(self) -> str | None:
        result = await self._session.execute(select(func.max(SFASeasonScore.season)))
        return result.scalar_one_or_none()

    async def latest_season_for_player(self, player_id: int) -> str | None:
        result = await self._session.execute(
            select(func.max(SFASeasonScore.season)).where(
                SFASeasonScore.player_id == player_id
            )
        )
        return result.scalar_one_or_none()
