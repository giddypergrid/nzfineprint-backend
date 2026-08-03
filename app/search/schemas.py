"""Request and response shapes for the search endpoint."""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Filters(BaseModel):
    """UI chips. Bind straight to indexed columns, so they gate the set before ranking."""
    event_category: Optional[str] = None
    action_taken: Optional[str] = None
    code: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_significance: Optional[int] = Field(default=None, ge=0, le=100)


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, description="Free-text query — keyword or natural language.")
    filters: Filters = Field(default_factory=Filters)
    limit: int = Field(default=20, ge=1, le=100)


class Notice(BaseModel):
    """One result row — the enriched record, source text included."""
    id: str
    date: Optional[date]
    type: Optional[str]
    headline: Optional[str]
    plain_english: Optional[str]
    event_category: Optional[str]
    action_taken: Optional[str]
    affected_parties: Optional[list] = None
    significance_score: Optional[int]
    significance_reason: Optional[str]
    title: Optional[str]
    fulltext: Optional[str]
    landing_url: Optional[str]
    score: Optional[float] = Field(default=None, description="Relevance score (semantic route only).")


class SearchResponse(BaseModel):
    route: str            # "keyword" | "semantic" — which path answered
    parsed: Optional[dict] = None   # what the LLM extracted (semantic route), for transparency
    count: int
    results: list[Notice]


class CorpusStats(BaseModel):
    """Quoted by the UI when a search finds nothing, so `newest` is the real last notice loaded —
    never "current"."""
    notice_count: int
    oldest: Optional[date]
    newest: Optional[date]
