"""Rate limiting for the paid routes. Counters live in Redis because each uvicorn worker is its own
process, so in-memory counts would be per-worker.

  per-IP minute     -> 429   burst limit
  per-IP day        -> 429   one visitor can't drain the day
  service day       -> 503   hard ceiling on LLM spend
  concurrent /ask   -> 503   per worker

Fails OPEN: a Redis outage allows traffic rather than taking the API down.
"""
import threading
from datetime import datetime, timezone

import redis
from fastapi import HTTPException, Request

from app import config as cfg

_redis = redis.from_url(cfg.REDIS_URL, decode_responses=True,
                        socket_connect_timeout=1, socket_timeout=1)

PER_MINUTE = int(cfg.RATE_PER_MINUTE)
PER_DAY = int(cfg.RATE_PER_DAY)


def _client_ip(request: Request) -> str:
    """Behind Cloudflare the real IP is the first X-Forwarded-For entry, not the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _hit(key: str, ttl_seconds: int) -> int:
    """One hit on a fixed-window key; the expiry is set on first use."""
    count = _redis.incr(key)
    if count == 1:
        _redis.expire(key, ttl_seconds)
    return count


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int((end_of_day - now).total_seconds()) + 1


def enforce_rate_limits(request: Request) -> None:
    """FastAPI dependency for the paid routes. 429 per-IP, 503 for the service cap."""
    try:
        ip = _client_ip(request)
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        ttl_day = _seconds_until_utc_midnight()

        minute_window = now.strftime("%Y-%m-%dT%H:%M")
        if _hit(f"rl:min:{ip}:{minute_window}", 60) > PER_MINUTE:
            raise HTTPException(429, "Slow down — too many requests in a minute. Try again shortly.",
                                headers={"Retry-After": "60"})

        if _hit(f"rl:day:{ip}:{today}", ttl_day) > PER_DAY:
            raise HTTPException(429, "You've reached today's request limit. Please try again tomorrow.",
                                headers={"Retry-After": str(ttl_day)})

        if _hit(f"rl:global:{today}", ttl_day) > cfg.GLOBAL_DAILY_CAP:
            raise HTTPException(503, "The desk has hit its daily limit. Please come back tomorrow.",
                                headers={"Retry-After": str(ttl_day)})

    except redis.RedisError:
        return   # fail open


# Non-blocking acquire: reject fast rather than make the caller wait 30s behind other runs.
_ask_slots = threading.BoundedSemaphore(cfg.ASK_CONCURRENCY)


def acquire_ask_slot() -> None:
    if not _ask_slots.acquire(blocking=False):
        raise HTTPException(503, "The desk is busy right now — please try again in a few seconds.",
                            headers={"Retry-After": "10"})


def release_ask_slot() -> None:
    try:
        _ask_slots.release()
    except ValueError:
        pass   # already released — never raise from cleanup
