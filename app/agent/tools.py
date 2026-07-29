"""The four read-only tools the agent can call. Compact-by-default: list tools return headlines +
ids, never fulltext. Full text only via get_notice. Backend owns every limit — the model never sets
how much we fetch. Reuses the existing search engine for the fan-out tool.
"""
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from app import config as cfg
from app.search import engine
from app.search.schemas import Filters

# Backend-owned caps. The model asks; these decide. Never let a tool argument raise them.
SEARCH_LIMIT = 12          # rows returned to the agent per search (compact scan)
HISTORY_LIMIT = 40         # max notices in one company timeline
RELATED_LIMIT = 15         # max other notices surfaced for a related party

_COMPACT_COLS = "id, date, headline, event_category, significance_score"


def _connect():
    return psycopg.connect(cfg.DATABASE_URL, row_factory=dict_row)


def search_notices(query: str, event_category: Optional[str] = None,
                   action_taken: Optional[str] = None, date_from: Optional[str] = None,
                   date_to: Optional[str] = None, min_significance: Optional[int] = None) -> list[dict]:
    """Wide, cheap scan. Returns compact rows (no fulltext) so the agent can triage many at once.
    Runs through the same hybrid keyword/semantic engine as /search."""
    filters = Filters(event_category=event_category, action_taken=action_taken,
                      date_from=date_from, date_to=date_to, min_significance=min_significance)
    result = engine.search_keyword(query, filters, SEARCH_LIMIT) \
        if not _is_sentence(query) else (engine.search_semantic(query, filters, SEARCH_LIMIT), "semantic")
    rows = result[0]
    return [_compact(r) for r in rows]


def get_notice(notice_id: str) -> Optional[dict]:
    """Drill into ONE notice — the full plain-language decode + source text + parties + link."""
    sql = """SELECT id, date, type, headline, plain_english, event_category, action_taken,
                    affected_parties, significance_score, significance_reason, title, fulltext,
                    landing_url
             FROM notices WHERE id = %(id)s"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, {"id": notice_id})
        return cur.fetchone()


def get_company_history(nzbn: Optional[str] = None, company_number: Optional[str] = None,
                        name: Optional[str] = None) -> list[dict]:
    """Every notice for one entity, oldest-first — the timeline. Match by id first (exact), else name."""
    params: dict = {"limit": HISTORY_LIMIT}
    if nzbn:
        where, params["v"] = "nzbn = %(v)s", nzbn
    elif company_number:
        where, params["v"] = "company_number = %(v)s", company_number
    elif name:
        where, params["v"] = "title ILIKE %(v)s", f"%{name}%"
    else:
        return []
    sql = f"SELECT {_COMPACT_COLS}, title FROM notices WHERE {where} ORDER BY date ASC LIMIT %(limit)s"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [_compact(r, keep_title=True) for r in cur.fetchall()]


def find_related_parties(notice_id: str) -> dict:
    """From one notice, pull the named parties, then find other notices that also name any of them —
    the entity-linking hop that surfaces repeat players."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT affected_parties FROM notices WHERE id = %(id)s", {"id": notice_id})
        row = cur.fetchone()
        parties = (row or {}).get("affected_parties") or []
        if not parties:
            return {"parties": [], "also_appearing": []}

        # Any notice (other than this one) whose parties overlap — jsonb containment via ?| on text[].
        cur.execute(
            f"""SELECT {_COMPACT_COLS}, affected_parties FROM notices
                WHERE id <> %(id)s AND affected_parties ?| %(names)s
                ORDER BY date DESC LIMIT %(limit)s""",
            {"id": notice_id, "names": [str(p) for p in parties], "limit": RELATED_LIMIT})
        return {"parties": parties, "also_appearing": [_compact(r) for r in cur.fetchall()]}


def _compact(row: dict, keep_title: bool = False) -> dict:
    """Trim a row to the scannable fields. Keeps context small so multi-step stays affordable."""
    out = {"id": row["id"], "date": str(row.get("date")), "headline": row.get("headline"),
           "category": row.get("event_category"), "significance": row.get("significance_score")}
    if keep_title:
        out["name"] = row.get("title")
    return out


def _is_sentence(query: str) -> bool:
    """Same word-count routing as /search — long queries go semantic inside search_notices too."""
    from app.search.query_parser import looks_like_sentence
    return looks_like_sentence(query)
