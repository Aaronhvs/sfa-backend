from pydantic import BaseModel, ConfigDict


class RankedPlayerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    id: int
    name: str
    team: str
    position: str
    competition: str
    sfa_pts: float
    matches: int
    photo_url: str | None


class RankingResponseSchema(BaseModel):
    season: str
    total: int
    ranking: list[RankedPlayerSchema]
