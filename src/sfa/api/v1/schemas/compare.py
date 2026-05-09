from pydantic import BaseModel

from sfa.api.v1.schemas.players import PlayerDetailSchema


class CompareResponseSchema(BaseModel):
    season: str
    player_a: PlayerDetailSchema
    player_b: PlayerDetailSchema
