"""Central config — env vars with sensible defaults, shared by every pipeline step."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # python-dotenv reads UTF-8 cleanly (avoids the gbk gotcha)

# --- DigitalNZ API ---
API_KEY = os.getenv("DIGITALNZ_API_KEY", "")
BASE_URL = os.getenv("DIGITALNZ_BASE_URL", "https://api.digitalnz.org/v3/records.json")
PRIMARY_COLLECTION = "New Zealand Gazette"
SOURCE_STAMP = "New Zealand Gazette (CC BY 3.0 NZ)"

# --- Postgres (matches docker-compose.yml) ---
# 127.0.0.1 not "localhost": on Windows, localhost resolves to IPv6 ::1 first and psycopg
# stalls ~8s before falling back to IPv4. The literal IP skips that entirely (~0.07s).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fineprint:fineprint@127.0.0.1:5432/fineprint")

# --- DeepSeek (enrichment) ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
ENRICH_CONCURRENCY = int(os.getenv("ENRICH_CONCURRENCY", "20"))

# --- Embeddings (vectorize) — hosted API, no local model, ~0 server RAM ---
# bge-m3: 1024-dim (matches vector(1024)), 8192-token context, takes NO instruction prefix.
# MUST be the same model app/search/embed.py uses at query time, or doc and query vectors live in
# different spaces and retrieval silently returns nonsense.
EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3")
# Measured on the full corpus: batch 64 -> 24 rows/s, 256 -> 69/s, 512 -> 85/s (diminishing after).
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "512"))                 # texts per API call
EMBED_CHUNK = int(os.getenv("EMBED_CHUNK", "2048"))                # rows read from DB per round-trip

EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
EMBED_API_BASE = os.getenv("EMBED_API_BASE", "https://openrouter.ai/api/v1")

# --- pull knobs (override via .env) ---
PER_PAGE = int(os.getenv("PULL_PER_PAGE", "100"))          # DigitalNZ hard max = 100
THROTTLE_SECONDS = float(os.getenv("PULL_THROTTLE_SECONDS", "1.0"))
START_YEAR = int(os.getenv("PULL_START_YEAR", "2000"))     # online archive begins 2000

# --- paths ---
DATA = ROOT / "data"
NOTICES_FILE = DATA / "notices.jsonl"
STATE_FILE = DATA / "notices.state.json"
LOAD_STATE_FILE = DATA / "load.state.json"    # how far into the jsonl load has already got

# --- Bucket-1 codes: single source of truth = reference/notice_types.json ---
_TYPES = json.loads((ROOT / "reference" / "notice_types.json").read_text(encoding="utf-8"))["types"]
TYPES = {t["code"]: t["label"] for t in _TYPES}                              # all 27 codes -> label
BUCKET1 = {t["code"]: t["label"] for t in _TYPES if t.get("mvp_insolvency")}  # insolvency subset (used later)
