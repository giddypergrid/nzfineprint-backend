"""Embed a query into a 1024-dim vector. The one place the embedding backend is chosen — hosted, so
the server holds zero model weight; swap this body to change it.

Must match Prep/pipeline/vectorize.py in BOTH model and prefix convention (bge-m3 takes no prefix,
bge-*-en-v1.5 needs a query/passage pair). A mismatch doesn't raise, it just returns worse results.
"""
from functools import lru_cache

from openai import OpenAI

from app import config as cfg


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    if not cfg.EMBED_API_KEY:
        raise RuntimeError("EMBED_API_KEY not set — semantic search unavailable.")
    return OpenAI(api_key=cfg.EMBED_API_KEY, base_url=cfg.EMBED_API_BASE)


def embed_query(text: str) -> list[float]:
    """Return the query's 1024-dim embedding. Raises if the embed API key isn't configured."""
    response = _client().embeddings.create(model=cfg.EMBED_MODEL, input=text)
    return response.data[0].embedding
