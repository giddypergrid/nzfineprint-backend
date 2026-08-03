"""App config — env vars with defaults. Self-contained: app/ never imports from Prep/, so values
that must agree with the offline pipeline are duplicated here to keep the two images independent."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Compose env wins — load_dotenv doesn't override what's already set.
load_dotenv(Path(__file__).resolve().parent / ".env")

# 127.0.0.1 for local dev; compose overrides to the `db` host.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fineprint:fineprint@127.0.0.1:5432/fineprint")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Changing only a filter re-sends the same query string; this skips the repeat parse.
SEMANTIC_PARSE_CACHE_SIZE = int(os.getenv("SEMANTIC_PARSE_CACHE_SIZE", "512"))

# MUST match the model Prep/pipeline/vectorize.py used, or query and document vectors live in
# different spaces and results are nonsense.
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
EMBED_API_BASE = os.getenv("EMBED_API_BASE", "https://openrouter.ai/api/v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3")

DEFAULT_LIMIT = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))
MAX_LIMIT = int(os.getenv("SEARCH_MAX_LIMIT", "100"))

# Where the updater publishes the corpus stats. Redis is the fast path; the TTL bounds how often a
# Redis miss can fall through to a full table scan.
STATS_KEY = os.getenv("STATS_KEY", "fineprint:stats")
STATS_CACHE_SECONDS = int(os.getenv("STATS_CACHE_SECONDS", "3600"))

# Set to the real frontend domain(s) in production.
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Off in production, or the whole schema is publicly browsable.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# Rate limits on the paid routes. Counters live in Redis so they hold across both uvicorn workers.
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
RATE_PER_MINUTE = os.getenv("RATE_PER_MINUTE", "10")           # per IP -> 429
RATE_PER_DAY = os.getenv("RATE_PER_DAY", "100")                # per IP -> 429
GLOBAL_DAILY_CAP = int(os.getenv("GLOBAL_DAILY_CAP", "500"))   # whole service -> 503
ASK_CONCURRENCY = int(os.getenv("ASK_CONCURRENCY", "3"))       # agent runs per worker -> 503 when full
API_THREADPOOL = int(os.getenv("API_THREADPOOL", "10"))        # sync-endpoint threads per worker
