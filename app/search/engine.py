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


# Trigram fallback fires when full-text finds nothing (usually a typo). word_similarity finds
# the best-matching word *portion* of the title, so a misspelled token still matches — unlike
# whole-string similarity, which dilutes on common words ("removal"). See [[search-design]].
TRIGRAM_THRESHOLD = 0.5   # min word_similarity to count as a fuzzy hit (0-1)


def search_keyword(query: str, filters: Filters, limit: int) -> tuple[list[dict], str]:
    """Full-text first (exact word stems). If that's empty — typically a typo — fall back to a
    trigram fuzzy match on the title. Returns (rows, route) so callers can show which one hit."""
    rows = _search_fulltext(query, filters, limit)
    if rows:
        return rows, "keyword"
    return _search_trigram(query, filters, limit), "keyword_fuzzy"


def _search_fulltext(query: str, filters: Filters, limit: int) -> list[dict]:
    """plainto_tsquery is punctuation-safe (O'Brien, co.) and ANDs the words. 'simple' config (no
    stemming) must match the search_vector column's config — see 02_indexes.sql.

    Rank = length-normalised ts_rank + significance - bulk-list penalty. Three problems, three terms:
      - Plain ts_rank counts term FREQUENCY, so a giant "800 companies to be removed" list (repeats a
        word dozens of times) buried the real single-company notice. The `1` flag divides by
        log(length) to undo that.
      - significance_score (0-100 -> 0-1) surfaces the notable event over routine filings.
      - BUT a mass strike-off of 10,521 companies is scored highly-significant AND happens to contain
        almost any name/word, so it rode significance back to the top. Its tell is LENGTH — a real
        notice is a few hundred chars, a mass list is tens of thousands. So subtract a penalty that
        maxes out (-1.0) for anything past ~20k chars, leaving real notices (<2k) barely touched.
    Verified: 'Du Val'/'Smiths City' return the real receivership first; 'liquidation' returns CBL,
    Blue Chip, Ruapehu; 'Sacred Hill'/'wine liquidation' no longer surface the bulk-removal lists."""
    params: dict = {"q": query, "limit": limit}
    conditions = ["search_vector @@ plainto_tsquery('simple', %(q)s)"]
    conditions += _filter_sql(filters, params)

    sql = f"""
        SELECT {_SELECT_COLS},
               ts_rank(search_vector, plainto_tsquery('simple', %(q)s), 1)
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


# Trigram fallback only runs on short, name-shaped titles. Long multi-company titles (dozens of
# names concatenated) always contain *some* substring similar to any short query word, so trigram
# false-matches on them — the documented "trigram degrades on long text" failure. A user fuzzy-
# searching a company name means a short title, so this cap both fixes accuracy and matches intent.
TRIGRAM_MAX_TITLE_LEN = 120


def _search_trigram(query: str, filters: Filters, limit: int) -> list[dict]:
    """Typo-tolerant fallback. EVERY meaningful query word must be word_similar to a title token
    (AND) — that's what rejects coincidental hits — and only short titles are eligible. Ranked by
    the sum of per-word similarities. See [[search-design]]: trigram is short-text-only."""
    words = [w for w in query.split() if len(w) >= 3]   # skip tiny stopwords; they add noise
    if not words:
        return []

    params: dict = {"thresh": TRIGRAM_THRESHOLD, "maxlen": TRIGRAM_MAX_TITLE_LEN, "limit": limit}
    scores, each_strong = [], []
    for i, word in enumerate(words):
        key = f"w{i}"
        params[key] = word
        scores.append(f"word_similarity(%({key})s, title)")
        each_strong.append(f"word_similarity(%({key})s, title) >= %(thresh)s")
    sum_score = " + ".join(scores)                                 # rank: total match strength

    # `<%` (word-similarity) gates use the trigram GIN index for fast entry; ANDed so every word
    # must match, consistent with the explicit score checks (session threshold is set to match).
    index_gates = [f"%({f'w{i}'})s <%% title" for i in range(len(words))]
    conditions = ["length(title) <= %(maxlen)s",
                  "(" + " AND ".join(index_gates) + ")",
                  "(" + " AND ".join(each_strong) + ")"]
    conditions += _filter_sql(filters, params)

    sql = f"""
        SELECT {_SELECT_COLS},
               ({sum_score}) AS score
        FROM notices
        {_where(conditions)}
        ORDER BY score DESC, date DESC
        LIMIT %(limit)s
    """
    with _connect() as connection, connection.cursor() as cursor:
        # Align the <% operator threshold with our explicit >= check (operator default is 0.6).
        # SET takes no bound params; TRIGRAM_THRESHOLD is our own float constant, so inlining is safe.
        cursor.execute(f"SET LOCAL pg_trgm.word_similarity_threshold = {TRIGRAM_THRESHOLD}")
        cursor.execute(sql, params)
        return cursor.fetchall()


# Semantic score is cosine similarity (0-1). When the LLM also surfaced literal keywords, rows
# whose text actually contains them get this flat bonus — so a match that is BOTH semantically
# close and literally on-topic outranks one that's only close in vector space. Small on purpose:
# vector meaning stays the primary signal, keywords only break near-ties.
KEYWORD_BONUS = 0.1


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
        params["kw"] = " | ".join(keywords)   # OR the terms — any keyword hit earns the bonus
        bonus_sql = (f"(CASE WHEN search_vector @@ plainto_tsquery('simple', %(kw)s) "
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
