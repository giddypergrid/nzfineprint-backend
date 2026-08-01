"""Run a search against the notices table. Two routes share one filter builder:

  keyword   -> full-text (search_vector @@ query) ranked by ts_rank, filters as index gates.
  semantic  -> same filters gate the set, then ORDER BY embedding <=> query_vector (cosine).

Filters bind to indexed columns (Prep/db/init/02_indexes.sql) so the gate is cheap; ranking
runs only over what survives the gate.
"""
from typing import Optional

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app import config as cfg
from app.search.embed import embed_query
from app.search.schemas import Filters

# Columns every result carries — one place so both routes return the same shape.
_SELECT_COLS = """
    id, date, type, headline, plain_english, event_category, action_taken,
    affected_parties, significance_score, significance_reason, title, fulltext, landing_url
"""


def _connect():
    connection = psycopg.connect(cfg.DATABASE_URL, row_factory=dict_row)
    register_vector(connection)   # so a python list binds as a pgvector literal
    return connection


def _filter_sql(filters: Filters, params: dict) -> list[str]:
    """Translate the caller's hard filters into SQL conditions, appending bound params.
    Returns a list of condition strings (AND-joined by the caller). Empty if no filters set."""
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


def search_keyword(query: str, filters: Filters, limit: int) -> tuple[list[dict], str]:
    """Exact phrase match, and nothing else — empty means the record genuinely has no such notice.

    A trigram typo fallback used to run here and was removed: measured against the live 205k rows it
    could not be separated from its own false positives by any threshold. "Bay Plumbing Limited"
    scored 0.810 against HOULAHAN PLUMBING LIMITED while a real rescue ("Sacrd Hill" -> SACRED HILL
    WINERY) scored only 0.643 — generic words carry most of the similarity, so a different company
    outranks the right one. word_similarity, strict_word_similarity and per-company matching against
    affected_parties all showed the same inversion; trigrams compare SETS, so word order can't help.
    Naming a wrong company to someone checking their own name costs more than making them retype.
    Returns (rows, route) so callers can still report which route answered."""
    return _search_fulltext(query, filters, limit), "keyword"


def _search_fulltext(query: str, filters: Filters, limit: int) -> list[dict]:
    """phraseto_tsquery requires the words ADJACENT ('bay' <-> 'plumbing'), not merely both present.
    plainto_tsquery only ANDs them, which let a query match words borrowed from three different
    companies inside one bulk-removal list: "Bay Plumbing Limited" hit a notice containing BAY
    RADIATORS, AUCKLAND DRAINAGE PLUMBING SERVICES and 39 other LIMITEDs, none of them the company
    searched for. Adjacency is what makes a zero-result answer trustworthy — and it still finds you
    when you ARE genuinely listed, because the names sit contiguously in the body text.
    Punctuation-safe (O'Brien, co.); 'simple' config (no stemming) must match search_vector's own
    config — see 02_indexes.sql.

    Rank = length-normalised ts_rank + significance - bulk-list penalty:
      - Plain ts_rank counts term FREQUENCY, so a giant "800 companies to be removed" list (repeats a
        word dozens of times) buried the real single-company notice. The `1` flag divides by
        log(length) to undo that.
      - significance_score (0-100 -> 0-1) surfaces the notable event over routine filings.
      - BUT a mass strike-off of 10,521 companies is scored highly-significant AND happens to contain
        almost any name/word, so it rode significance back to the top. Its tell is LENGTH — a real
        notice is a few hundred chars, a mass list is tens of thousands. The penalty maxes out (-1.0)
        past ~20k chars. Adjacency already handles multi-word queries; this still earns its keep on
        SINGLE-word ones ("liquidation"), where a phrase is just the one term and can't discriminate.
    Verified: 'Du Val'/'Smiths City' return the real receivership first; 'liquidation' returns CBL,
    Blue Chip, Ruapehu; 'Sacred Hill'/'wine liquidation' no longer surface the bulk-removal lists."""
    params: dict = {"q": query, "limit": limit}
    conditions = ["search_vector @@ phraseto_tsquery('simple', %(q)s)"]
    conditions += _filter_sql(filters, params)

    sql = f"""
        SELECT {_SELECT_COLS},
               ts_rank(search_vector, phraseto_tsquery('simple', %(q)s), 1)
                 + COALESCE(significance_score, 0) / 100.0
                 - LEAST(length(COALESCE(fulltext, '')) / 20000.0, 1.0) AS score
        FROM notices
        {_where(conditions)}
        ORDER BY score DESC, date DESC
        LIMIT %(limit)s
    """
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


# Semantic score is cosine similarity (0-1). When the LLM also surfaced literal keywords, rows
# whose text actually contains them get this flat bonus — so a match that is BOTH semantically
# close and literally on-topic outranks one that's only close in vector space. Small on purpose:
# vector meaning stays the primary signal, keywords only break near-ties.
KEYWORD_BONUS = 0.1


def _keyword_tsquery_input(keywords: list[str]) -> str:
    """Build websearch_to_tsquery input: '"Hawkes Bay" or "wine"'. Quotes keep a multi-word keyword
    a phrase instead of loose words; `or` is a real disjunction. The previous ' | '.join fed into
    plainto_tsquery, which silently drops operators and ANDs everything — so the bonus quietly
    required EVERY keyword to hit rather than any one."""
    cleaned = (keyword.replace('"', " ").strip() for keyword in keywords)
    return " or ".join(f'"{keyword}"' for keyword in cleaned if keyword)


def search_semantic(semantic_query: str, filters: Filters, limit: int,
                    keywords: Optional[list[str]] = None) -> list[dict]:
    """Vector route. Filters gate the set first, then rank survivors by cosine similarity to the
    query embedding, plus a small keyword bonus (hybrid) when the LLM extracted literal terms."""
    query_vector = Vector(embed_query(semantic_query))   # wrap so psycopg sends it as vector, not float[]
    params: dict = {"vec": query_vector, "limit": limit}

    conditions = ["embedding IS NOT NULL"]
    conditions += _filter_sql(filters, params)

    # Hybrid: base cosine + KEYWORD_BONUS if the row's full-text matches the extracted keywords.
    bonus_sql = "0"
    if keywords:
        params["kw"] = _keyword_tsquery_input(keywords)
        bonus_sql = (f"(CASE WHEN search_vector @@ websearch_to_tsquery('simple', %(kw)s) "
                     f"THEN {KEYWORD_BONUS} ELSE 0 END)")

    sql = f"""
        SELECT {_SELECT_COLS},
               (1 - (embedding <=> %(vec)s)) + {bonus_sql} AS score
        FROM notices
        {_where(conditions)}
        ORDER BY score DESC
        LIMIT %(limit)s
    """
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()
