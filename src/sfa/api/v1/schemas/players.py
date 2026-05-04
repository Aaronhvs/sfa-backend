from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BreakdownEntrySchema(BaseModel):
    count: int
    pts: float


class PlayerDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    team: str
    position: str
    competition: str
    sfa_pts: float
    matches: int
    photo_url: str | None
    global_rank: int
    season: str
    breakdown: dict[str, BreakdownEntrySchema] | None
    competitions: list[str]


class PlayerEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition: str
    stage: str
    fixture_id: int
    home_team: str
    away_team: str
    played_at: datetime
    minute: int
    event_type: str
    score_before: str | None
    score_diff: int | None
    m1: float
    m2: float
    m3: float
    m4: float
    mvisit: float
    pts: float


class PlayerFixtureSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixture_id: int
    competition: str
    stage: str
    home_team: str
    away_team: str
    played_at: datetime
    sfa_pts: float
    events_count: int
