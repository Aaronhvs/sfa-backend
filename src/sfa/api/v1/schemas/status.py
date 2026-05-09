from pydantic import BaseModel


class StatusResponseSchema(BaseModel):
    status: str
    season: str | None
    players: int
    scores: int
    competitions: int
    events: int
    api_version: str
