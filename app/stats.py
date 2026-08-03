"""Corpus stats: Redis first, Postgres as the fallback.

Redis is an optimisation, not a dependency. The nightly updater publishes the numbers
(Prep/pipeline/refresh_stats.py) and the normal request just reads them — but a miss, whether from a
cold deploy, a restart or an eviction, falls through to the DB, caches the answer in-process, and
writes it back so the next request is served from Redis again.

That write-back is why no deploy step is needed to seed Redis: the first request repopulates it.
"""
import json
import time

import redis

from app import config as cfg
from app.search import engine

_redis = redis.from_url(cfg.REDIS_URL, decode_responses=True,
                        socket_connect_timeout=1, socket_timeout=1)

_process_cache: tuple[float, dict] | None = None


def corpus_stats() -> dict:
    """Always returns. The in-process cache is what makes a Redis outage cheap: without it every
    request would scan the table; with it the worst case is one scan per worker per TTL."""
    global _process_cache
    if _process_cache and time.monotonic() - _process_cache[0] < cfg.STATS_CACHE_SECONDS:
        return _process_cache[1]

    stats = _read_redis() or _rebuild_from_db()
    _process_cache = (time.monotonic(), stats)
    return stats


def _read_redis() -> dict | None:
    try:
        raw = _redis.get(cfg.STATS_KEY)
    except redis.RedisError:
        return None
    return json.loads(raw) if raw else None


def _rebuild_from_db() -> dict:
    """Scan, then republish. A failed write-back is not fatal — the in-process cache still absorbs
    the load until the nightly refresh puts it right."""
    stats = engine.compute_corpus_stats()
    try:
        _redis.set(cfg.STATS_KEY, json.dumps(stats, default=str))
    except redis.RedisError:
        pass
    return stats
