#!/bin/sh
# Nightly database backup, run INSIDE the prep/updater container.
#   scheduled : Prep/crontab
#   manual    : docker compose run --rm prep sh run_backup.sh
#
# -Fc (custom format) because pg_restore can then do the phased schema-only/data-only restore that
# a plain SQL dump cannot — see the restore notes in the project's critical-changes memory.
set -e

stamp() { date '+%Y-%m-%d %H:%M:%S %Z'; }

BACKUP_DIR=${BACKUP_DIR:-/app/data/backups}   # bind-mounted to ./Prep/data, so it outlives the container
KEEP=${BACKUP_KEEP:-5}                        # ~1.1GB per dump — 5 is about 5.5GB

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/fineprint-$(date +%Y%m%d-%H%M%S).dump"

echo "[$(stamp)] pg_dump -> $target"
# Write to .partial and rename only on success, so an interrupted dump can never be mistaken for a
# good backup by the retention step below.
pg_dump -Fc -d "$DATABASE_URL" -f "$target.partial"
mv "$target.partial" "$target"
echo "[$(stamp)] wrote $(du -h "$target" | cut -f1)"

echo "[$(stamp)] keeping the newest $KEEP"
ls -1t "$BACKUP_DIR"/fineprint-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    echo "[$(stamp)] pruning $(basename "$old")"
    rm -f "$old"
done

echo "[$(stamp)] backup complete"
