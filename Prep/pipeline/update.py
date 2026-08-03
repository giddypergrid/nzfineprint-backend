"""
Daily update: pull -> load -> enrich, in sequence. Brings the DB current with the Gazette.

Every stage does only the delta:
  - pull   re-checks the current year, appending new notices to notices.jsonl
  - load   upserts on id, so existing rows are untouched
  - enrich fills only rows where enriched_at IS NULL

Safe to repeat; a quiet day is a near no-op. A failing stage stops the run so nothing enriches
against a half-loaded DB.

Run from the Prep/ folder, or schedule it (cron / Task Scheduler):
  python -m pipeline.update
"""
import sys
import time

from pipeline import pull, load, enrich


def run_stage(name, fn):
    """Run one pipeline stage, timed, with a clear banner. Re-raises on failure to stop the chain."""
    print(f"\n{'=' * 60}\n  {name}\n{'=' * 60}")
    started = time.time()
    fn()
    print(f"  {name} done in {(time.time() - started) / 60:.1f} min")


def main():
    if len(sys.argv) > 1:                              # stages read sys.argv — don't let flags leak in
        raise SystemExit("update.py takes no arguments — run stages directly to pass their flags.")

    overall = time.time()
    run_stage("PULL  (DigitalNZ -> notices.jsonl)", pull.main)
    run_stage("LOAD  (notices.jsonl -> Postgres)", load.main)
    run_stage("ENRICH (fill new rows via DeepSeek)", enrich.main)
    print(f"\nDaily update complete in {(time.time() - overall) / 60:.1f} min.")


if __name__ == "__main__":
    main()
