#!/bin/bash
# PostgreSQL Database Backup Script
# Usage: bash backend/scripts/backup_db.sh
# Saves a pg_dump to backend/data/backups/postgres/ and keeps the last 10 backups.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../data/backups/postgres"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/tsushin_pg_backup_${TIMESTAMP}.sql"

echo "[Backup] Starting PostgreSQL backup..."

if ! docker ps --format '{{.Names}}' | grep -q '^tsushin-postgres$'; then
    echo "[Backup] FAILED — tsushin-postgres container is not running"
    exit 1
fi

docker exec tsushin-postgres pg_dump -U tsushin tsushin > "$BACKUP_FILE" 2>/dev/null

if [ $? -eq 0 ] && [ -s "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[Backup] PostgreSQL backup saved: $BACKUP_FILE ($SIZE)"
    # Keep only last 10 backups
    ls -t "$BACKUP_DIR"/tsushin_pg_backup_*.sql 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
    echo "[Backup] Cleanup complete — keeping last 10 backups"
else
    echo "[Backup] FAILED — pg_dump returned empty or errored"
    rm -f "$BACKUP_FILE"
    exit 1
fi
