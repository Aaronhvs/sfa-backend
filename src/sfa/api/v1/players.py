from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.api.v1.schemas.players import (
    BreakdownEntrySchema,
    PlayerDetailSchema,
    PlayerEventSchema,
    PlayerFixtureSchema,
)
from sfa.core.dependencies import get_db
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.events.models import PlayerEvent
from sfa.infrastructure.models.fixtures.models import Fixture
from sfa.infrastructure.models.players.models import Player
from sfa.infrastructure.models.scores.models import SFASeasonScore
from sfa.infrastructure.models.teams.models import Team

router = APIRouter()

HomeTeam = Team.__table__.alias("home_team")
AwayTeam = Team.__table__.alias("away_team")


async def _get_player_detail(
    player_id: int,
    db: AsyncSession,
    season: str | None = None,
) -> PlayerDetailSchema:
    # Resolve latest season if not provided
    if season is None:
        result = await db.execute(
            select(func.max(SFASeasonScore.season)).where(
                SFASeasonScore.player_id == player_id
            )
        )
        season = result.scalar_one_or_none()

    # Primary score row for the player (pick competition with highest pts)
    score_stmt = (
        select(
            Player.id,
            Player.name,
            Team.name.label("team"),
            Player.position,
            Competition.name.label("competition"),
            SFASeasonScore.total_pts.label("sfa_pts"),
            SFASeasonScore.matches_played.label("matches"),
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
    row = (await db.execute(score_stmt)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Player not found")

    # Global rank via subquery: COUNT of players with higher total_pts
    rank_stmt = select(func.count()).where(
        SFASeasonScore.player_id != player_id,
        SFASeasonScore.season == season,
        SFASeasonScore.total_pts > row["sfa_pts"],
    )
    global_rank = (await db.execute(rank_stmt)).scalar_one() + 1

    # Competitions list for this player and season
    comp_stmt = (
        select(Competition.name)
        .join(SFASeasonScore, SFASeasonScore.competition_id == Competition.id)
        .where(
            SFASeasonScore.player_id == player_id,
            SFASeasonScore.season == season,
        )
    )
    competitions = list((await db.execute(comp_stmt)).scalars().all())

    raw_breakdown: dict | None = row["breakdown"]
    breakdown: dict[str, BreakdownEntrySchema] | None = None
    if raw_breakdown:
        breakdown = {
            k: BreakdownEntrySchema(**v) for k, v in raw_breakdown.items()
            if isinstance(v, dict) and "count" in v and "pts" in v
        }

    return PlayerDetailSchema(
        id=row["id"],
        name=row["name"],
        team=row["team"],
        position=str(row["position"]),
        competition=row["competition"],
        sfa_pts=float(row["sfa_pts"]),
        matches=row["matches"],
        photo_url=row["photo_url"],
        global_rank=global_rank,
        season=season or "",
        breakdown=breakdown,
        competitions=competitions,
    )


@router.get("/players/{player_id}", response_model=PlayerDetailSchema)
async def get_player(
    player_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    season: str | None = Query(default=None),
):
    return await _get_player_detail(player_id, db, season)


@router.get("/players/{player_id}/events", response_model=list[PlayerEventSchema])
async def get_player_events(
    player_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    season: str | None = Query(default=None),
    competition_id: int | None = Query(default=None),
):
    home_alias = Team.__table__.alias("ht")
    away_alias = Team.__table__.alias("at")

    stmt = (
        select(
            PlayerEvent.id,
            Competition.name.label("competition"),
            Fixture.stage,
            Fixture.id.label("fixture_id"),
            home_alias.c.name.label("home_team"),
            away_alias.c.name.label("away_team"),
            Fixture.played_at,
            PlayerEvent.minute,
            PlayerEvent.event_type,
            PlayerEvent.score_before,
            PlayerEvent.score_diff,
            PlayerEvent.m1,
            PlayerEvent.m2,
            PlayerEvent.m3,
            PlayerEvent.m4,
            PlayerEvent.mvisit,
            PlayerEvent.pts,
        )
        .join(Fixture, PlayerEvent.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(home_alias, Fixture.home_team_id == home_alias.c.id)
        .join(away_alias, Fixture.away_team_id == away_alias.c.id)
        .where(PlayerEvent.player_id == player_id)
        .order_by(Fixture.played_at.desc(), PlayerEvent.minute.asc())
    )

    if season is not None:
        stmt = stmt.where(Fixture.season == season)
    if competition_id is not None:
        stmt = stmt.where(Fixture.competition_id == competition_id)

    rows = (await db.execute(stmt)).mappings().all()
    return [PlayerEventSchema(**dict(row)) for row in rows]


@router.get("/players/{player_id}/fixtures", response_model=list[PlayerFixtureSchema])
async def get_player_fixtures(
    player_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    season: str | None = Query(default=None),
    competition_id: int | None = Query(default=None),
):
    home_alias = Team.__table__.alias("ht")
    away_alias = Team.__table__.alias("at")

    stmt = (
        select(
            Fixture.id.label("fixture_id"),
            Competition.name.label("competition"),
            Fixture.stage,
            home_alias.c.name.label("home_team"),
            away_alias.c.name.label("away_team"),
            Fixture.played_at,
            func.sum(PlayerEvent.pts).label("sfa_pts"),
            func.count(PlayerEvent.id).label("events_count"),
        )
        .join(Fixture, PlayerEvent.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(home_alias, Fixture.home_team_id == home_alias.c.id)
        .join(away_alias, Fixture.away_team_id == away_alias.c.id)
        .where(PlayerEvent.player_id == player_id)
        .group_by(
            Fixture.id,
            Competition.name,
            Fixture.stage,
            home_alias.c.name,
            away_alias.c.name,
            Fixture.played_at,
        )
        .order_by(Fixture.played_at.desc())
    )

    if season is not None:
        stmt = stmt.where(Fixture.season == season)
    if competition_id is not None:
        stmt = stmt.where(Fixture.competition_id == competition_id)

    rows = (await db.execute(stmt)).mappings().all()
    return [PlayerFixtureSchema(**dict(row)) for row in rows]
