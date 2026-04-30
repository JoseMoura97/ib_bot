#!/bin/bash
set -euo pipefail

BACKUP_DIR="/home/ibbot/backups"
PROJECT_DIR="/home/ibbot/ib_bot"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/ibbot_db_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

cd "$PROJECT_DIR"
docker compose exec -T db pg_dump -U ibbot ibbot | gzip > "$BACKUP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file is empty: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "$(date -Iseconds) Backup OK: $BACKUP_FILE ($SIZE)"

find "$BACKUP_DIR" -name "ibbot_db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "$(date -Iseconds) Cleaned backups older than ${RETENTION_DAYS} days"
