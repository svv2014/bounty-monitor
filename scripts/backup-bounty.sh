#!/usr/bin/env bash
# Copies bounty.db to a timestamped backup in the same directory (or BACKUP_DIR).
set -euo pipefail

DB="${BOUNTY_DB_PATH:-bounty.db}"
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$DB")}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
DEST="${BACKUP_DIR}/bounty-${TIMESTAMP}.db"

if [[ ! -f "$DB" ]]; then
  echo "ERROR: database not found: $DB" >&2
  exit 1
fi

cp "$DB" "$DEST"
echo "Backed up $DB → $DEST"
