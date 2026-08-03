"""Embed each enriched notice into its `embedding` column via the hosted API.

Embeds `plain_english`, not `fulltext` — the LLM decode already stripped the legal boilerplate, so
the vector carries meaning rather than shared template noise. Only enriched-but-unembedded rows are
touched, which makes it resumable.

Same hosted endpoint embeds documents here and queries at search time, so both sides are guaranteed
to share a vector space. Switching to a bge-*-en-v1.5 model means adding prefixes on BOTH sides or
retrieval silently degrades.

  read EMBED_CHUNK rows -> embed in EMBED_BATCH-sized calls -> write the chunk back

Run from Prep/:
  python -m pipeline.vectorize --limit 100
  python -m pipeline.vectorize
"""
import argparse
import json
import time
import urllib.error
import urllib.request

import psycopg
from pgvector.psycopg import register_vector

from shared import config as cfg

COUNT_READY = "SELECT count(*) FROM notices WHERE plain_english IS NOT NULL AND embedding IS NULL"
SELECT_CHUNK = """
SELECT id, plain_english FROM notices
WHERE plain_english IS NOT NULL AND embedding IS NULL
ORDER BY id LIMIT %s
"""
UPDATE_EMBEDDING = "UPDATE notices SET embedding = %s WHERE id = %s"

MAX_RETRIES = 5


def embed_texts_via_api(texts):
    """One API call; vectors come back in input order. Retries with backoff so a whole chunk isn't
    lost to one blip."""
    payload = json.dumps({"model": cfg.EMBED_MODEL, "input": texts}).encode("utf-8")
    request = urllib.request.Request(f"{cfg.EMBED_API_BASE}/embeddings", data=payload, headers={
        "Authorization": f"Bearer {cfg.EMBED_API_KEY}",
        "Content-Type": "application/json",
    })

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.load(response)
            ordered = sorted(data["data"], key=lambda item: item["index"])

            # JSON returns exact 0/1 as ints, and psycopg refuses a mixed int/float list.
            return [[float(component) for component in item["embedding"]] for item in ordered]

        except Exception as error:
            if attempt == MAX_RETRIES:
                raise
            wait_seconds = 2 ** attempt
            print(f"    embed failed ({error}) — retry {attempt}/{MAX_RETRIES} in {wait_seconds}s")
            time.sleep(wait_seconds)


def embed_and_store_one_chunk(cursor, connection, rows):
    """Embed a chunk of (id, plain_english) rows via the API, write the vectors back."""
    ids = [row[0] for row in rows]
    texts = [row[1] for row in rows]

    vectors = []
    for start in range(0, len(texts), cfg.EMBED_BATCH):
        vectors.extend(embed_texts_via_api(texts[start:start + cfg.EMBED_BATCH]))

    for notice_id, vector in zip(ids, vectors):
        cursor.execute(UPDATE_EMBEDDING, (vector, notice_id))
    connection.commit()


def main():
    parser = argparse.ArgumentParser(description="Embed enriched notices via the hosted API.")
    parser.add_argument("--limit", type=int, help="Only process this many rows (for testing).")
    args = parser.parse_args()

    if not cfg.EMBED_API_KEY:
        raise SystemExit("EMBED_API_KEY not set — add it to Prep/.env")

    print(f"Embedding with {cfg.EMBED_MODEL} via {cfg.EMBED_API_BASE}")

    connection = psycopg.connect(cfg.DATABASE_URL)
    register_vector(connection)                       # lets psycopg send python lists as vectors
    cursor = connection.cursor()

    cursor.execute(COUNT_READY)
    total = cursor.fetchone()[0]
    if args.limit:
        total = min(total, args.limit)
    print(f"Embedding {total} notices  (chunk {cfg.EMBED_CHUNK}, batch {cfg.EMBED_BATCH})...")

    done = 0
    started = time.time()
    while done < total:
        take = min(cfg.EMBED_CHUNK, total - done)
        cursor.execute(SELECT_CHUNK, (take,))
        rows = cursor.fetchall()
        if not rows:
            break

        embed_and_store_one_chunk(cursor, connection, rows)
        done += len(rows)
        rate = done / (time.time() - started)
        eta_min = (total - done) / rate / 60 if rate else 0
        print(f"  {done}/{total}  {rate:.0f}/s  eta {eta_min:.1f} min", flush=True)

    print(f"Done -> {done} embedded in {(time.time() - started) / 60:.1f} min.")
    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()
