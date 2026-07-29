"""Rate limiting for the paid routes, backed by Redis so the counts stay correct across the two
uvicorn workers (each worker is a separate process with its own memory — see docker-compose.yml).

Four guards:
  - per-IP per-minute   -> 429  (a human burst limit)
  - per-IP per-day      -> 429  (one visitor can't drain the day)
  - whole-service/day   -> 503  (a hard daily budget ceiling on LLM spend)
  - concurrent /ask runs -> 503 (per worker; reject fast instead of queueing 30s behind others)

Fail-OPEN by design: if Redis is unreachable we allow the request rather than take the API down —
availability matters more than a perfectly enforced limit for a demo.
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
    """The visitor's IP. Behind a proxy/Cloudflare the real IP is the first X-Forwarded-For entry;
    otherwise it's the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _hit(key: str, ttl_seconds: int) -> int:
    """Count one hit against a fixed-window key, setting the window's expiry on first use."""
    count = _redis.incr(key)
    if count == 1:
        _redis.expire(key, ttl_seconds)
    return count


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int((end_of_day - now).total_seconds()) + 1


def enforce_rate_limits(request: Request) -> None:
    """FastAPI dependency for the paid routes. Raises 429 (per-IP) / 503 (service cap). Fails open
    on any Redis error so an outage never blocks traffic."""
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
        return   # fail open — don't let a Redis blip take the API down


# Per-worker cap on simultaneous agent runs. Non-blocking acquire: reject fast with a 503 rather
# than making the caller wait 30s behind others (2 workers x ASK_CONCURRENCY = the global ceiling).
_ask_slots = threading.BoundedSemaphore(cfg.ASK_CONCURRENCY)


def acquire_ask_slot() -> None:
    if not _ask_slots.acquire(blocking=False):
        raise HTTPException(503, "The desk is busy right now — please try again in a few seconds.",
                            headers={"Retry-After": "10"})


def release_ask_slot() -> None:
    try:
        _ask_slots.release()
    except ValueError:
        pass   # already released — never raise from a cleanup path
