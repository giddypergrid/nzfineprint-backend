"""
Load data/notices.jsonl into Postgres. Upsert on id, so re-running is always safe.

Delta by default: a byte offset records how far the last run got, and only lines appended after it
are read. Without it every nightly run re-upserted all 205k rows — 25 minutes of writes to add ~180
notices, growing every year.

Run from the Prep/ folder, or via `docker compose run --rm prep python -m pipeline.load`:
  python -m pipeline.load          # only what pull appended since last time
  python -m pipeline.load --all    # whole file, ignoring the checkpoint
"""
import argparse
import json

import psycopg

from shared import config as cfg

BATCH_SIZE = 1000

UPSERT = """
INSERT INTO notices (id, code, type, date, title, nzbn, company_number, fulltext, landing_url, source)
VALUES (%(id)s, %(code)s, %(type)s, %(date)s, %(title)s, %(nzbn)s, %(company_number)s,
        %(fulltext)s, %(landing_url)s, %(source)s)
ON CONFLICT (id) DO UPDATE SET
    code = EXCLUDED.code, type = EXCLUDED.type, date = EXCLUDED.date, title = EXCLUDED.title,
    nzbn = EXCLUDED.nzbn, company_number = EXCLUDED.company_number, fulltext = EXCLUDED.fulltext,
    landing_url = EXCLUDED.landing_url, source = EXCLUDED.source;
"""


def read_offset() -> int:
    """Where the last run stopped. Falls back to 0 if the file has shrunk, which means pull --reset
    rewrote it and every byte is new again."""
    if not cfg.LOAD_STATE_FILE.exists():
        return 0
    offset = json.loads(cfg.LOAD_STATE_FILE.read_text(encoding="utf-8")).get("offset", 0)
    return offset if offset <= cfg.NOTICES_FILE.stat().st_size else 0


def write_offset(offset: int) -> None:
    cfg.LOAD_STATE_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def read_rows_from(start_offset: int):
    """Yield (row, offset_after_row) from start_offset onward.

    Binary mode on purpose: text-mode tell() is disabled while iterating a file, so the offset is
    accumulated from raw line lengths instead."""
    with cfg.NOTICES_FILE.open("rb") as handle:
        handle.seek(start_offset)
        offset = start_offset
        for raw_line in handle:
            offset += len(raw_line)
            line = raw_line.strip()
            if line:
                yield json.loads(line.decode("utf-8")), offset


def main():
    parser = argparse.ArgumentParser(description="Upsert notices.jsonl into Postgres.")
    parser.add_argument("--all", action="store_true", help="Ignore the checkpoint, load everything.")
    args = parser.parse_args()

    start_offset = 0 if args.all else read_offset()
    print(f"Loading from byte {start_offset:,} of {cfg.NOTICES_FILE.stat().st_size:,}")

    connection = psycopg.connect(cfg.DATABASE_URL)
    cursor = connection.cursor()

    batch, loaded, offset = [], 0, start_offset
    for row, row_end in read_rows_from(start_offset):
        batch.append(row)
        offset = row_end
        if len(batch) == BATCH_SIZE:
            loaded += commit_batch(cursor, connection, batch, offset)
            print(f"  loaded {loaded}")
            batch = []

    if batch:
        loaded += commit_batch(cursor, connection, batch, offset)

    print(f"Done -> {loaded} rows upserted into notices.")
    cursor.close()
    connection.close()


def commit_batch(cursor, connection, batch, offset) -> int:
    """Upsert, then checkpoint. That order means a crash re-does at most one batch, which is
    harmless because the upsert is idempotent."""
    cursor.executemany(UPSERT, batch)
    connection.commit()
    write_offset(offset)
    return len(batch)


if __name__ == "__main__":
    main()
