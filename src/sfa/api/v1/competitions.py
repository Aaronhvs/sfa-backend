from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.api.v1.schemas.competitions import (
    CompetitionSchema,
    StandingEntrySchema,
    StandingsResponseSchema,
)
from sfa.core.dependencies import get_db
from sfa.infrastructure.models.competitions.models import Competition
from sfa.infrastructure.models.standings.models import StandingSnapshot
from sfa.infrastructure.models.teams.models import Team

router = APIRouter()


@router.get("/competitions", response_model=list[CompetitionSchema])
async def list_competitions(db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(
        Competition.id,
        Competition.name,
        Competition.country,
        Competition.competition_factor.label("factor"),
    ).order_by(Competition.name)
    rows = (await db.execute(stmt)).mappings().all()
    return [CompetitionSchema(**dict(row)) for row in rows]


@router.get(
    "/competitions/{competition_id}/standings",
    response_model=StandingsResponseSchema,
)
async def get_standings(
    competition_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    season: str | None = Query(default=None),
    matchday: int | None = Query(default=None),
):
    # Verify competition exists
    comp_result = await db.execute(
        select(Competition.name).where(Competition.id == competition_id)
    )
    competition_name = comp_result.scalar_one_or_none()
    if competition_name is None:
        raise HTTPException(status_code=404, detail="Competition not found")

    # Resolve latest season if not provided
    if season is None:
        result = await db.execute(
            select(func.max(StandingSnapshot.season)).where(
                StandingSnapshot.competition_id == competition_id
            )
        )
        season = result.scalar_one_or_none()
        if season is None:
            raise HTTPException(status_code=404, detail="No standings found for this competition")

    # Resolve latest matchday if not provided
    if matchday is None:
        result = await db.execute(
            select(func.max(StandingSnapshot.matchday)).where(
                StandingSnapshot.competition_id == competition_id,
                StandingSnapshot.season == season,
            )
        )
        matchday = result.scalar_one_or_none()
        if matchday is None:
            raise HTTPException(
                status_code=404,
                detail="No standings found for the given season",
            )

    stmt = (
        select(
            StandingSnapshot.position,
            Team.name.label("team"),
            StandingSnapshot.points,
        )
        .join(Team, StandingSnapshot.team_id == Team.id)
        .where(
            StandingSnapshot.competition_id == competition_id,
            StandingSnapshot.season == season,
            StandingSnapshot.matchday == matchday,
        )
        .order_by(StandingSnapshot.position)
    )
    rows = (await db.execute(stmt)).mappings().all()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No standings found for the given season and matchday",
        )

    return StandingsResponseSchema(
        competition=competition_name,
        season=season,
        matchday=matchday,
        standings=[StandingEntrySchema(**dict(row)) for row in rows],
    )
