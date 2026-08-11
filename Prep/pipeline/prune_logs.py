"""Drop request-log files older than the retention window.

Same shape as the pg_dump retention in run_backup.sh: the API only ever appends, and this is the one
thing that deletes, so the log can't quietly fill the disk.

  python -m pipeline.prune_logs            # keep REQUEST_LOG_RETENTION_DAYS (default 30)
"""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_DIR = Path(os.getenv("REQUEST_LOG_DIR", "data/logs"))
RETENTION_DAYS = int(os.getenv("REQUEST_LOG_RETENTION_DAYS", "30"))

# requests-2026-08-11.jsonl — the date in the NAME is the key, not the file's mtime, which an
# append can move forward at any time.
LOG_NAME = re.compile(r"^requests-(\d{4}-\d{2}-\d{2})\.jsonl$")


def main():
    if not LOG_DIR.exists():
        print(f"no log dir at {LOG_DIR} — nothing to prune")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).date()
    kept, pruned = 0, 0

    for path in sorted(LOG_DIR.glob("requests-*.jsonl")):
        match = LOG_NAME.match(path.name)
        if not match:
            continue
        if datetime.strptime(match.group(1), "%Y-%m-%d").date() < cutoff:
            print(f"pruning {path.name}")
            path.unlink()
            pruned += 1
        else:
            kept += 1

    print(f"request logs: kept {kept}, pruned {pruned} (retention {RETENTION_DAYS} days)")


if __name__ == "__main__":
    main()
