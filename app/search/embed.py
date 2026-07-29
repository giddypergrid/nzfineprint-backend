"""Embed a search query into a 1024-dim vector via a hosted embedding endpoint.

This is the ONE place the embedding backend is chosen. Today it's a hosted OpenAI-compatible API
(OpenRouter, model baai/bge-m3) so the server holds zero model weight. To switch to an in-process
model or a self-hosted endpoint, replace only this function's body — nothing else in the app changes.

bge-m3 takes NO instruction prefix, and Prep/pipeline/vectorize.py embeds documents the same way.
Both sides must always use the same model AND the same prefix convention: bge-*-en-v1.5 models need
an asymmetric query/passage prefix pair, bge-m3 needs none. Mismatching them does not raise — it
quietly returns worse results.
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
