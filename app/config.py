"""App config — env vars with defaults. Self-contained: app/ is its own container, does not
import from Prep/. Values that must agree with the offline pipeline (model name, DB url) are
duplicated here on purpose so the two images stay independently buildable."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load app/.env regardless of the working directory. In the container, env vars from compose
# take precedence (load_dotenv doesn't override values already set in the environment).
load_dotenv(Path(__file__).resolve().parent / ".env")

# Postgres — 127.0.0.1 default for local dev; compose overrides to the `db` service host.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fineprint:fineprint@127.0.0.1:5432/fineprint")

# Query parser — DeepSeek, same provider/pattern as offline enrichment (deliberate non-Anthropic).
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Query embedding — hosted bge-m3 (OpenAI-compatible), 1024-dim, no instruction prefix.
# MUST be the same model Prep/pipeline/vectorize.py used on the documents, or the vectors live in
# different spaces and results are nonsense. Both sides read this same model id from their .env.
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
EMBED_API_BASE = os.getenv("EMBED_API_BASE", "https://openrouter.ai/api/v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3")

# Retrieval knobs.
DEFAULT_LIMIT = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))
MAX_LIMIT = int(os.getenv("SEARCH_MAX_LIMIT", "100"))

# CORS — comma-separated origins allowed to call the API from a browser. Defaults to the local
# Vite dev server; set to the real frontend domain(s) in production.
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Interactive API docs (/docs, /redoc, /openapi.json). On by default for local dev; set to
# "false" in production to stop the whole schema being publicly browsable.
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# --- Rate limiting on the paid LLM routes (/search semantic, /ask). Counters live in Redis so they
# stay accurate across the 2 uvicorn workers. All tunable via env without a code change. ---
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
RATE_PER_MINUTE = os.getenv("RATE_PER_MINUTE", "10")            # per-IP burst limit -> 429
RATE_PER_DAY = os.getenv("RATE_PER_DAY", "100")                # per-IP daily limit -> 429
GLOBAL_DAILY_CAP = int(os.getenv("GLOBAL_DAILY_CAP", "500"))   # whole-service daily budget -> 503
ASK_CONCURRENCY = int(os.getenv("ASK_CONCURRENCY", "3"))       # concurrent agent runs per worker -> 503 when full
API_THREADPOOL = int(os.getenv("API_THREADPOOL", "10"))        # sync-endpoint worker threads per uvicorn worker
