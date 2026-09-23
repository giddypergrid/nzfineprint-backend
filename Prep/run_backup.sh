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
KEEP=${BACKUP_KEEP:-3}                        # nightly dumps kept, ~1.1GB each
KEEP_WEEKLY=${BACKUP_KEEP_WEEKLY:-4}          # weekly dumps kept, so bad data noticed late is still recoverable
WEEKLY_DAY=${BACKUP_WEEKLY_DAY:-7}            # ISO weekday that also files a weekly: 1 = Mon ... 7 = Sun
WEEKLY_DIR="$BACKUP_DIR/weekly"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/fineprint-$(date +%Y%m%d-%H%M%S).dump"

echo "[$(stamp)] pg_dump -> $target"
# Write to .partial and rename only on success, so an interrupted dump can never be mistaken for a
# good backup by the retention step below.
pg_dump -Fc -d "$DATABASE_URL" -f "$target.partial"
mv "$target.partial" "$target"
echo "[$(stamp)] wrote $(du -h "$target" | cut -f1)"

# A hard link gives the same file a second name: no extra disk, and it survives the daily prune.
if [ "$(date +%u)" = "$WEEKLY_DAY" ]; then
    mkdir -p "$WEEKLY_DIR"
    ln "$target" "$WEEKLY_DIR/$(basename "$target")"
    echo "[$(stamp)] filed as weekly"
fi

prune() {
    echo "[$(stamp)] keeping the newest $2 in $1"
    ls -1t "$1"/fineprint-*.dump 2>/dev/null | tail -n +$(($2 + 1)) | while read -r old; do
        echo "[$(stamp)] pruning $(basename "$old")"
        rm -f "$old"
    done
}
prune "$BACKUP_DIR" "$KEEP"
prune "$WEEKLY_DIR" "$KEEP_WEEKLY"

echo "[$(stamp)] backup complete"
