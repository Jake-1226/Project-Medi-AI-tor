#!/bin/bash
# Medi-AI-tor Backup Script (#55)
# Backs up fleet state, audit logs, knowledge base, and metric history
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DATA_DIR="${DATA_DIR:-./data}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/medi-ai-tor-backup-${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "=== Medi-AI-tor Backup ==="
echo "Timestamp: $TIMESTAMP"
echo "Source:    $DATA_DIR"
echo "Target:    $BACKUP_FILE"

# Create compressed archive of data directory
if [ -d "$DATA_DIR" ]; then
    tar -czf "$BACKUP_FILE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created: $BACKUP_FILE ($SIZE)"
else
    echo "WARNING: Data directory $DATA_DIR not found — nothing to back up"
    exit 0
fi

# Prune old backups (keep last 30)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/medi-ai-tor-backup-*.tar.gz 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 30 ]; then
    ls -1t "$BACKUP_DIR"/medi-ai-tor-backup-*.tar.gz | tail -n +31 | xargs rm -f
    echo "Pruned old backups (kept latest 30)"
fi

echo "=== Backup complete ==="
