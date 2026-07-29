"""
Enrich every notice into structured fields (headline, plain_english, event_category,
action_taken, affected_parties, significance_score, significance_reason) via DeepSeek.

Resumable: only pulls rows where enriched_at IS NULL, so a re-run (or a crash) just continues.
Concurrent (ENRICH_CONCURRENCY workers) — DeepSeek allows up to 2,500 connections on this model.
The system prompt is byte-identical every call, so DeepSeek's prompt cache makes input ~50x cheaper.

Run from the Prep/ folder:
  python -m pipeline.enrich --limit 20   # test on 20 rows first, prints each result
  python -m pipeline.enrich              # full run, all unenriched rows
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import psycopg
from openai import OpenAI

from shared import config as cfg
from pipeline.enrich_prompt import SYSTEM_PROMPT, EVENT_CATEGORIES, ACTION_TYPES

COMMIT_EVERY = 100   # main-thread commits per this many completed rows (crash loses at most this)

SELECT_UNENRICHED = "SELECT id, type, title, fulltext FROM notices WHERE enriched_at IS NULL"

UPDATE_ENRICHED = """
UPDATE notices SET
    headline = %(headline)s, plain_english = %(plain_english)s,
    event_category = %(event_category)s, action_taken = %(action_taken)s,
    affected_parties = %(affected_parties)s, significance_score = %(significance_score)s,
    significance_reason = %(significance_reason)s, enriched_at = %(enriched_at)s
WHERE id = %(id)s
"""


def coerce_to_enum(value, allowed):
    """Return value if it's a valid enum member, else 'other' — never trust the model blindly."""
    return value if value in allowed else "other"


def build_enriched_row(notice_id, model_json):
    """Model's JSON -> a validated row dict ready for UPDATE. Clamps/normalizes every field."""
    score = int(model_json.get("significance_score", 0))
    parties = model_json.get("affected_parties") or []

    return {
        "id": notice_id,
        "headline": (model_json.get("headline") or "").strip(),
        "plain_english": (model_json.get("plain_english") or "").strip(),
        "event_category": coerce_to_enum(model_json.get("event_category"), EVENT_CATEGORIES),
        "action_taken": coerce_to_enum(model_json.get("action_taken"), ACTION_TYPES),
        "affected_parties": json.dumps(parties if isinstance(parties, list) else []),
        "significance_score": max(0, min(100, score)),
        "significance_reason": (model_json.get("significance_reason") or "").strip(),
        "enriched_at": datetime.now(timezone.utc),
    }


def enrich_one_notice(client, row):
    """Call DeepSeek for one notice; return a validated row dict, or None on any failure."""
    notice_id, notice_type, title, fulltext = row
    user_prompt = f"Notice type: {notice_type}\nCompany/subject: {title}\n\nFull text:\n{fulltext}"

    try:
        response = client.chat.completions.create(
            model=cfg.DEEPSEEK_MODEL,
            response_format={"type": "json_object"},
            max_tokens=1000,   # 500 truncated list-heavy notices (ds/ba/pn) -> Unterminated string
            extra_body={"thinking": {"type": "disabled"}},  # flash reasons by default -> pure latency for extraction
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        model_json = json.loads(response.choices[0].message.content)
        return build_enriched_row(notice_id, model_json)
    except Exception as error:
        print(f"  [skip] {notice_id}: {error}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Enrich notices via DeepSeek.")
    parser.add_argument("--limit", type=int, help="Only process this many rows (for testing).")
    args = parser.parse_args()

    if not cfg.DEEPSEEK_API_KEY:
        raise SystemExit("Missing DEEPSEEK_API_KEY — check .env")

    connection = psycopg.connect(cfg.DATABASE_URL)
    cursor = connection.cursor()
    query = SELECT_UNENRICHED + (f" LIMIT {args.limit}" if args.limit else "")
    cursor.execute(query)
    rows = cursor.fetchall()
    print(f"Enriching {len(rows)} notices ({cfg.ENRICH_CONCURRENCY} workers)...")

    client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)
    done = 0

    total = len(rows)
    started = time.time()

    # Workers ONLY call the API (write-free, thread-safe). The main thread below is the
    # single writer — commits every COMMIT_EVERY rows so a crash loses at most that many.
    with ThreadPoolExecutor(max_workers=cfg.ENRICH_CONCURRENCY) as pool:
        futures = [pool.submit(enrich_one_notice, client, row) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            if result:
                cursor.execute(UPDATE_ENRICHED, result)
                if args.limit:                        # test mode -> show the actual output
                    print(f"  {result['id']}  [{result['significance_score']}] "
                          f"{result['event_category']}: {result['headline']}")
            done += 1
            if done % COMMIT_EVERY == 0:
                connection.commit()
                if not args.limit:
                    rate = done / (time.time() - started)
                    eta_min = (total - done) / rate / 60 if rate else 0
                    print(f"  {done}/{total}  {rate:.1f}/s  eta {eta_min:.0f} min")

    connection.commit()                               # flush the final partial batch
    print(f"Done -> {done} processed in {(time.time() - started) / 60:.1f} min.")
    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()
