"""
Load data/notices.jsonl into Postgres. Upsert on id, so re-running is always safe —
a notice already in the DB just gets overwritten with the same (or newer) values.

Run from the Prep/ folder (locally), or via `docker compose run --rm prep python -m pipeline.load`:
  python -m pipeline.load
"""
import json

import psycopg

from shared import config as cfg

UPSERT = """
INSERT INTO notices (id, code, type, date, title, nzbn, company_number, fulltext, landing_url, source)
VALUES (%(id)s, %(code)s, %(type)s, %(date)s, %(title)s, %(nzbn)s, %(company_number)s,
        %(fulltext)s, %(landing_url)s, %(source)s)
ON CONFLICT (id) DO UPDATE SET
    code = EXCLUDED.code, type = EXCLUDED.type, date = EXCLUDED.date, title = EXCLUDED.title,
    nzbn = EXCLUDED.nzbn, company_number = EXCLUDED.company_number, fulltext = EXCLUDED.fulltext,
    landing_url = EXCLUDED.landing_url, source = EXCLUDED.source;
"""


def read_rows_from_jsonl():
    """Yield one notice dict per line — reads lazily so the whole file is never in memory at once."""
    with cfg.NOTICES_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def main():
    connection = psycopg.connect(cfg.DATABASE_URL)
    cursor = connection.cursor()

    batch = []
    loaded = 0
    for row in read_rows_from_jsonl():
        batch.append(row)
        if len(batch) == 1000:
            cursor.executemany(UPSERT, batch)
            connection.commit()
            loaded += len(batch)
            print(f"  loaded {loaded}")
            batch = []

    if batch:
        cursor.executemany(UPSERT, batch)
        connection.commit()
        loaded += len(batch)

    print(f"Done -> {loaded} rows upserted into notices.")
    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()
