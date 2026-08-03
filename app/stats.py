"""Corpus stats, read from Redis only.

The updater recomputes and publishes them after each nightly load (Prep/pipeline/refresh_stats.py),
so the API never runs count(*) over the whole table for a number that changes once a day.

No DB fallback on purpose: falling back would reintroduce the scan on exactly the requests where
Redis is already struggling. Redis keeps the key through restarts (appendonly) and through memory
pressure (volatile-lru only evicts keys with a TTL) — see docker-compose.yml.
"""
import json

import redis

from app import config as cfg

_redis = redis.from_url(cfg.REDIS_URL, decode_responses=True,
                        socket_connect_timeout=1, socket_timeout=1)


def corpus_stats() -> dict | None:
    """None when the key is missing or Redis is unreachable; the caller turns that into a 503."""
    try:
        raw = _redis.get(cfg.STATS_KEY)
    except redis.RedisError:
        return None
    return json.loads(raw) if raw else None
