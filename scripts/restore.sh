#!/bin/bash
# Medi-AI-tor Restore Script (#55)
set -euo pipefail

BACKUP_FILE="${1:-}"
DATA_DIR="${DATA_DIR:-./data}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    echo "Available backups:"
    ls -lh ./backups/medi-ai-tor-backup-*.tar.gz 2>/dev/null || echo "  (none found)"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "=== Medi-AI-tor Restore ==="
echo "Source: $BACKUP_FILE"
echo "Target: $DATA_DIR"
echo ""
read -p "This will OVERWRITE existing data. Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

# Backup current data before overwriting
if [ -d "$DATA_DIR" ]; then
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    mv "$DATA_DIR" "${DATA_DIR}.pre-restore-${TIMESTAMP}"
    echo "Existing data moved to ${DATA_DIR}.pre-restore-${TIMESTAMP}"
fi

# Restore
tar -xzf "$BACKUP_FILE" -C "$(dirname "$DATA_DIR")"
echo "=== Restore complete ==="
echo "Restart the application to load restored data."
