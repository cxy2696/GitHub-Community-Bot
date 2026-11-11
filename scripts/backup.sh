#!/usr/bin/env bash
# Safe online SQLite backup using Python's stdlib backup API.
set -euo pipefail

DB="${1:-data/community.db}"
DEST="${2:-backups}"

if [[ ! -f "$DB" ]]; then
  echo "Database not found: $DB" >&2
  exit 1
fi

mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/community-$STAMP.db"
TMP="$OUT.tmp"

cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

DB="$DB" OUT="$TMP" python3 - <<'PY'
import os
import sqlite3

source = sqlite3.connect(os.environ["DB"])
target = sqlite3.connect(os.environ["OUT"])
try:
    with target:
        source.backup(target)
    result = target.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise SystemExit(f"integrity check failed: {result}")
finally:
    target.close()
    source.close()
PY

gzip -f "$TMP"
mv "$TMP.gz" "$OUT.gz"
echo "Backup written: $OUT.gz"
