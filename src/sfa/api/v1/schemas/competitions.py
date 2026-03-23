from pydantic import BaseModel, ConfigDict


class CompetitionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str
    factor: float


class StandingEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    team: str
    points: int


class StandingsResponseSchema(BaseModel):
    competition: str
    season: str
    matchday: int
    standings: list[StandingEntrySchema]
