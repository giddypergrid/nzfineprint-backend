"""Turn a raw search box string into a routing decision + (for natural-language queries) filters.

Two routes:
  keyword    — short, name/term-shaped. No LLM. Words map straight to the full-text index.
  semantic   — sentence-shaped ("a wine business that had to appoint someone..."). An LLM
               (DeepSeek, same as enrichment) extracts hard filters + a cleaned semantic phrase,
               because the filter intent is implied, not literally present as index-matchable words.

Routing is word-count only (<=4 words -> keyword): keeps the LLM off the majority of real queries
(people type 2-3 words), so most searches are near-instant and free.
"""
import json
from functools import lru_cache

from openai import OpenAI

from app import config as cfg
from app.search.facets import EVENT_CATEGORIES, ACTION_TYPES

_MAX_KEYWORD_WORDS = 3  # at/under this -> keyword route; above -> LLM parse + semantic


def looks_like_sentence(text: str) -> bool:
    """True if the query reads like natural language (needs LLM parsing), False if keyword-shaped.
    Word count only: short queries are name/term lookups, long ones are descriptions. A misrouted
    short query still searches fine on the keyword side (exact phrase match over title + body)."""
    return len(text.split()) > _MAX_KEYWORD_WORDS


_PARSE_SYSTEM_PROMPT = f"""You convert a person's plain-language search into a structured query \
for Fine Print, a search over New Zealand Gazette notices (official records of company \
liquidations, receiverships, removals, land and legal notices).

Return a JSON object with EXACTLY these keys:

- "semantic_query": string. The user's intent rewritten as a clean descriptive phrase for \
semantic matching, with filler removed. Keep the meaning; drop words that are captured by the \
filters below.

- "event_category": one of {EVENT_CATEGORIES}, or null if the query doesn't clearly imply one.
- "action_taken": one of {ACTION_TYPES}, or null if not clearly implied.
- "keywords": array of 0-4 specific literal terms worth an exact text match (a company name, a \
place, a distinctive word). Empty array if the query is purely conceptual.

Only set a filter when the query genuinely implies it — a wrong filter hides correct results. \
When unsure, use null and let the semantic match do the work.

Respond with ONLY the JSON object. No preamble, no code fences."""


def parse_semantic_query(text: str) -> dict:
    """LLM-parse a natural-language query into {semantic_query, event_category, action_taken, keywords}.
    Falls back to a filter-free semantic search if the model/JSON misbehaves.

    Successful parses are cached by exact query string, so re-searching with only a filter changed
    costs no LLM call. A failed parse deliberately raises past the cache: caching the degraded
    fallback would pin one DeepSeek outage to that query for the life of the process."""
    try:
        parsed = _parse_via_llm(text)
    except Exception:
        parsed = {}
    return dict(_shape(parsed, text))   # copy — callers must not be able to mutate the cached dict


@lru_cache(maxsize=cfg.SEMANTIC_PARSE_CACHE_SIZE)
def _parse_via_llm(text: str) -> dict:
    """Raw DeepSeek extraction. Raises on transport/JSON failure so nothing gets cached."""
    client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=cfg.DEEPSEEK_MODEL,
        response_format={"type": "json_object"},
        max_tokens=300,
        extra_body={"thinking": {"type": "disabled"}},  # flash reasons by default; off for extraction
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    )
    return json.loads(response.choices[0].message.content)


def _shape(parsed: dict, text: str) -> dict:
    """Force whatever the model returned into the contract the search pipeline relies on."""
    return {
        "semantic_query": (parsed.get("semantic_query") or text).strip(),
        "event_category": _valid(parsed.get("event_category"), EVENT_CATEGORIES),
        "action_taken": _valid(parsed.get("action_taken"), ACTION_TYPES),
        "keywords": [k for k in (parsed.get("keywords") or []) if isinstance(k, str)][:4],
    }


def _valid(value, allowed):
    """Keep a parsed enum only if it's a real member; anything else (incl. 'null') becomes None."""
    return value if value in allowed else None
