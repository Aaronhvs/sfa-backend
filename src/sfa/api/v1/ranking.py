from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.api.v1.schemas.ranking import RankedPlayerSchema, RankingResponseSchema
from sfa.core.dependencies import get_db
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore
from sfa.infrastructure.models.teams.models import Team

router = APIRouter()


async def _latest_season(db: AsyncSession) -> str | None:
    result = await db.execute(select(func.max(SFASeasonScore.season)))
    return result.scalar_one_or_none()


@router.get("/ranking", response_model=RankingResponseSchema)
async def get_ranking(
    db: Annotated[AsyncSession, Depends(get_db)],
    season: str | None = Query(default=None, description="Temporada, ej: 2024-25"),
    position: str | None = Query(default=None, description="Posición: DEL, EXT, MC, DC, LAT, GK"),
    competition_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    if season is None:
        season = await _latest_season(db)

    rank_col = func.rank().over(order_by=SFASeasonScore.total_pts.desc()).label("rank")

    home_team = Team.__table__.alias("t")
    stmt = (
        select(
            rank_col,
            Player.id,
            Player.name,
            Team.name.label("team"),
            Player.position,
            Competition.name.label("competition"),
            SFASeasonScore.total_pts.label("sfa_pts"),
            SFASeasonScore.matches_played.label("matches"),
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

    rows = (await db.execute(stmt)).mappings().all()

    # total count (without limit)
    count_stmt = (
        select(func.count())
        .select_from(SFASeasonScore)
        .join(Player, SFASeasonScore.player_id == Player.id)
        .where(SFASeasonScore.season == season)
    )
    if position is not None:
        count_stmt = count_stmt.where(Player.position == position)
    if competition_id is not None:
        count_stmt = count_stmt.where(SFASeasonScore.competition_id == competition_id)

    total = (await db.execute(count_stmt)).scalar_one()

    ranking = [RankedPlayerSchema(**dict(row)) for row in rows]
    return RankingResponseSchema(season=season or "", total=total, ranking=ranking)
