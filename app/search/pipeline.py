"""The one entry point: raw query + filters -> results. Decides the route, then runs it.

  1. Route: keyword-shaped query -> full-text (no LLM). Sentence-shaped -> LLM parse.
  2. On the semantic route the LLM may also surface hard filters (implied category/action) and
     literal keywords; the caller's explicit filters always win over inferred ones.
"""
from app.search import engine, query_parser
from app.search.schemas import Filters, SearchResponse


def run_search(query: str, filters: Filters, limit: int) -> SearchResponse:
    if not query_parser.looks_like_sentence(query):
        rows, route = engine.search_keyword(query, filters, limit)   # route: keyword | keyword_fuzzy
        return SearchResponse(route=route, count=len(rows), results=rows)

    parsed = query_parser.parse_semantic_query(query)
    merged = _merge_filters(filters, parsed)   # explicit UI filters override inferred ones
    rows = engine.search_semantic(parsed["semantic_query"], merged, limit, parsed["keywords"])
    return SearchResponse(route="semantic", parsed=parsed, count=len(rows), results=rows)


def _merge_filters(explicit: Filters, parsed: dict) -> Filters:
    """Layer LLM-inferred filters under the caller's explicit ones — explicit always wins."""
    merged = explicit.model_copy()
    if merged.event_category is None:
        merged.event_category = parsed.get("event_category")
    if merged.action_taken is None:
        merged.action_taken = parsed.get("action_taken")
    return merged
