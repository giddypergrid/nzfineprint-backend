"""
Recompute the corpus stats and publish them to Redis.

Runs last in the nightly update, so /stats never touches Postgres — count(*) scans the whole table
and the answer only changes once a day. Written with NO TTL: Redis runs volatile-lru, which evicts
only keys that have one, so the rate-limit counters go first and this key never does.

Run from the Prep/ folder:
  python -m pipeline.refresh_stats
"""
import json

import psycopg
import redis

from shared import config as cfg

TOTALS = "SELECT count(*), min(date), max(date) FROM notices"
PER_YEAR = """
SELECT EXTRACT(YEAR FROM date)::int, count(*)::int
FROM notices WHERE date IS NOT NULL
GROUP BY 1 ORDER BY 1
"""


def build_stats(cursor) -> dict:
    """in : an open cursor
    out: {"notice_count": int, "oldest": "YYYY-MM-DD", "newest": ..., "yearly": [{year, count}]}"""
    cursor.execute(TOTALS)
    notice_count, oldest, newest = cursor.fetchone()
    cursor.execute(PER_YEAR)
    return {
        "notice_count": notice_count,
        "oldest": str(oldest) if oldest else None,
        "newest": str(newest) if newest else None,
        "yearly": [{"year": year, "count": count} for year, count in cursor.fetchall()],
    }


def main():
    with psycopg.connect(cfg.DATABASE_URL) as connection, connection.cursor() as cursor:
        stats = build_stats(cursor)

    redis.from_url(cfg.REDIS_URL).set(cfg.STATS_KEY, json.dumps(stats))
    print(f"stats -> {cfg.STATS_KEY}: {stats['notice_count']} notices, "
          f"{stats['oldest']} to {stats['newest']}, {len(stats['yearly'])} years")


if __name__ == "__main__":
    main()
