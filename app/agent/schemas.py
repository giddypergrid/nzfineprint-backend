"""Request and response shapes for the /ask (agent) endpoint."""
from pydantic import BaseModel, Field

from app.search.schemas import Notice


class AskRequest(BaseModel):
    q: str = Field(..., min_length=1, description="The question to research over the public record.")


class AskResponse(BaseModel):
    """What the desk hands back: its stage-by-stage narration, the report, and the notices it read."""
    steps: list[str]
    answer: str
    sources: list[Notice]
