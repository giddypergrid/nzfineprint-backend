"""One JSON line per request: the call, who made it, what came back, and how long it took.

Written to be read *after* something looks wrong — so a line carries the whole package rather than a
summary. For /ask that means every stage line the agent emitted and the notices it cited, which is
what makes a bad answer explainable a week later.

IPs are salted-hashed, never stored raw. The log can still tell one visitor running fifty searches
from fifty visitors, without being a list of who looked up whom — which matters on a site whose whole
subject is what the public record says about people.
"""
import hashlib
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config as cfg

_write_lock = threading.Lock()      # two uvicorn workers append to the same file
_salt_cache: str | None = None


def _salt() -> str:
    """Stable across restarts or the hashes are meaningless. Env wins; otherwise persist one."""
    global _salt_cache
    if _salt_cache is not None:
        return _salt_cache

    _salt_cache = os.getenv("REQUEST_LOG_SALT", "")
    if not _salt_cache:
        salt_file = cfg.REQUEST_LOG_DIR / ".salt"
        if salt_file.exists():
            _salt_cache = salt_file.read_text(encoding="utf-8").strip()
        else:
            _salt_cache = secrets.token_hex(16)
            cfg.REQUEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
            salt_file.write_text(_salt_cache, encoding="utf-8")
    return _salt_cache


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{_salt()}{ip}".encode("utf-8")).hexdigest()[:16]


def describe_client(request) -> dict:
    """Who made the call, in the coarsest form that still answers "was this one person?"."""
    headers = request.headers
    forwarded = headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown")
    return {
        "ip_hash": _hash_ip(ip),
        "country": headers.get("cf-ipcountry"),          # set by Cloudflare, absent in dev
        "ua": (headers.get("user-agent") or "")[:200],
        "referer": headers.get("referer"),
    }


class Entry:
    """Mutable record for one request. The endpoint fills in `response` and anything extra."""

    def __init__(self, route: str, client: dict, request_payload: dict):
        self.route = route
        self.client = client
        self.request = request_payload
        self.response: dict | None = None
        self.status = 200
        self.extra: dict = {}


def _log_path() -> "os.PathLike":
    """One file per UTC day — the prune step keys off the date in the name."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return cfg.REQUEST_LOG_DIR / f"requests-{day}.jsonl"


def write_entry(entry: Entry, elapsed_ms: int) -> None:
    """Append one line. Logging must never be the reason a request fails, so this swallows its own
    errors — a full disk should cost the audit trail, not the API."""
    if not cfg.REQUEST_LOG_ENABLED:
        return

    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "route": entry.route,
        **entry.client,
        "request": entry.request,
        "response": entry.response,
        "status": entry.status,
        "ms": elapsed_ms,
        **entry.extra,
    }
    try:
        cfg.REQUEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _write_lock, _log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


@contextmanager
def record(route: str, request, request_payload: dict):
    """Wrap an endpoint body. Times it, captures the status of whatever was raised, and writes the
    line on the way out — including when the endpoint failed, which is when the log earns its keep."""
    entry = Entry(route, describe_client(request), request_payload)
    started_at = time.perf_counter()
    try:
        yield entry
    except Exception as error:
        entry.status = getattr(error, "status_code", 500)
        entry.extra["error"] = str(error)[:300]
        raise
    finally:
        write_entry(entry, round((time.perf_counter() - started_at) * 1000))
