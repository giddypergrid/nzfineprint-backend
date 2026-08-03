"""Search the notices table. Two routes share one filter builder:

  keyword   -> full-text phrase match, ranked by ts_rank
  semantic  -> same filters, ranked by embedding <=> query_vector (cosine)

Filters bind to indexed columns (Prep/db/init/02_indexes.sql), so the gate is cheap and ranking
runs only over survivors. Relevance picks the rows; the page lists them newest-first.
"""
from typing import Optional

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app import config as cfg
from app.search.embed import embed_query
from app.search.schemas import Filters

# One shape for every route.
_SELECT_COLS = """
    id, date, type, headline, plain_english, event_category, action_taken,
    affected_parties, significance_score, significance_reason, title, fulltext, landing_url
"""


def _connect():
    connection = psycopg.connect(cfg.DATABASE_URL, row_factory=dict_row)
    register_vector(connection)   # so a python list binds as a pgvector literal
    return connection


def _filter_sql(filters: Filters, params: dict) -> list[str]:
    """Hard filters -> AND-able SQL conditions, appending their bound params."""
    conditions = []
    if filters.event_category:
        conditions.append("event_category = %(event_category)s")
        params["event_category"] = filters.event_category
    if filters.action_taken:
        conditions.append("action_taken = %(action_taken)s")
        params["action_taken"] = filters.action_taken
    if filters.code:
        conditions.append("code = %(code)s")
        params["code"] = filters.code
    if filters.date_from:
        conditions.append("date >= %(date_from)s")
        params["date_from"] = filters.date_from
    if filters.date_to:
        conditions.append("date <= %(date_to)s")
        params["date_to"] = filters.date_to
    if filters.min_significance is not None:
        conditions.append("significance_score >= %(min_significance)s")
        params["min_significance"] = filters.min_significance
    return conditions


def _where(conditions: list[str]) -> str:
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""


def _rank_then_newest_first(score_sql: str, conditions: list[str]) -> str:
    """Rank inside, sort by date outside — two stages, not one.

    A single `ORDER BY date DESC LIMIT n` would drop relevance entirely: on the semantic route
    nothing in WHERE depends on the query, so every search would return the same newest n rows."""
    return f"""
        SELECT * FROM (
            SELECT {_SELECT_COLS}, {score_sql} AS score
            FROM notices
            {_where(conditions)}
            ORDER BY score DESC, date DESC
            LIMIT %(limit)s
        ) ranked
        ORDER BY date DESC
    """


_STATS_TOTALS = "SELECT count(*) AS notice_count, min(date) AS oldest, max(date) AS newest FROM notices"
_STATS_PER_YEAR = """
    SELECT EXTRACT(YEAR FROM date)::int AS year, count(*)::int AS count
    FROM notices WHERE date IS NOT NULL
    GROUP BY 1 ORDER BY 1
"""


def compute_corpus_stats() -> dict:
    """Scans the table, so callers must cache — this is the fallback for when Redis has nothing,
    not the request path. See app/stats.py."""
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(_STATS_TOTALS)
        totals = cursor.fetchone()
        cursor.execute(_STATS_PER_YEAR)
        yearly = cursor.fetchall()

    return {
        "notice_count": totals["notice_count"],
        "oldest": str(totals["oldest"]) if totals["oldest"] else None,
        "newest": str(totals["newest"]) if totals["newest"] else None,
        "yearly": yearly,
    }


def get_notice(notice_id: str) -> Optional[dict]:
    """Shared by /notices/{id} and the agent's drill-in tool so both return identical records."""
    sql = f"SELECT {_SELECT_COLS} FROM notices WHERE id = %(id)s"
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, {"id": notice_id})
        return cursor.fetchone()


def search_keyword(query: str, filters: Filters, limit: int) -> tuple[list[dict], str]:
    """Exact phrase only — empty means the record genuinely has no such notice.

    A trigram typo fallback was removed: generic words carry most of the similarity, so a wrong
    company consistently outscored the right one and no threshold separated them. Naming the wrong
    company to someone checking their own name costs more than making them retype.
    Returns (rows, route) so callers can report which route answered."""
    return _search_fulltext(query, filters, limit), "keyword"


def _search_fulltext(query: str, filters: Filters, limit: int) -> list[dict]:
    """phraseto_tsquery requires the words ADJACENT; plainto_tsquery only ANDs them, which let a
    query borrow its words from three different companies inside one bulk-removal list. Adjacency
    is what makes a zero result trustworthy. 'simple' must match search_vector's own config.

    Score = ts_rank(..., 1) + significance - length penalty:
      - flag 1 divides by log(length); plain ts_rank counts frequency, so bulk lists buried real hits
      - significance surfaces the notable event over routine filings
      - but a mass strike-off scores high AND contains almost any word; its tell is length, so the
        penalty maxes out past ~20k chars. Earns its keep on single-word queries, where a phrase
        is one term and can't discriminate."""
    params: dict = {"q": query, "limit": limit}
    conditions = ["search_vector @@ phraseto_tsquery('simple', %(q)s)"]
    conditions += _filter_sql(filters, params)

    score_sql = """ts_rank(search_vector, phraseto_tsquery('simple', %(q)s), 1)
                     + COALESCE(significance_score, 0) / 100.0
                     - LEAST(length(COALESCE(fulltext, '')) / 20000.0, 1.0)"""
    sql = _rank_then_newest_first(score_sql, conditions)
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


# Flat bonus for rows that also match the LLM's literal keywords. Small on purpose: vector meaning
# stays the primary signal, keywords only break near-ties.
KEYWORD_BONUS = 0.1


def _keyword_tsquery_input(keywords: list[str]) -> str:
    """Build websearch_to_tsquery input: '"Hawkes Bay" or "wine"'. Quotes keep a multi-word keyword
    a phrase; `or` is a real disjunction. plainto_tsquery silently drops operators and ANDs
    everything, which quietly required EVERY keyword to hit."""
    cleaned = (keyword.replace('"', " ").strip() for keyword in keywords)
    return " or ".join(f'"{keyword}"' for keyword in cleaned if keyword)


def search_semantic(semantic_query: str, filters: Filters, limit: int,
                    keywords: Optional[list[str]] = None) -> list[dict]:
    """Vector route: filters gate the set, then cosine similarity ranks it, plus a keyword bonus."""
    query_vector = Vector(embed_query(semantic_query))   # wrap so psycopg sends a vector, not float[]
    params: dict = {"vec": query_vector, "limit": limit}

    conditions = ["embedding IS NOT NULL"]
    conditions += _filter_sql(filters, params)

    bonus_sql = "0"
    if keywords:
        params["kw"] = _keyword_tsquery_input(keywords)
        bonus_sql = (f"(CASE WHEN search_vector @@ websearch_to_tsquery('simple', %(kw)s) "
                     f"THEN {KEYWORD_BONUS} ELSE 0 END)")

    sql = _rank_then_newest_first(f"(1 - (embedding <=> %(vec)s)) + {bonus_sql}", conditions)
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()
