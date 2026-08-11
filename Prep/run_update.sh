#!/bin/sh
# The daily update sequence, run INSIDE the prep container. One source of truth for both the
# scheduler (Prep/crontab) and a manual run (docker compose run --rm prep sh run_update.sh).
#   update    = pull -> load -> enrich (delta only; a quiet day is a near no-op)
#   vectorize = embed the rows enrich just added (WHERE embedding IS NULL)
set -e

stamp() { date '+%Y-%m-%d %H:%M:%S %Z'; }

echo "[$(stamp)] daily update: pull -> load -> enrich"
python -m pipeline.update

echo "[$(stamp)] vectorize: embedding new rows"
python -m pipeline.vectorize

echo "[$(stamp)] refresh stats -> redis"
python -m pipeline.refresh_stats

echo "[$(stamp)] prune request logs past retention"
python -m pipeline.prune_logs

echo "[$(stamp)] daily update complete"
