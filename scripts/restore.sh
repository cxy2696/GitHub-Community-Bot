#!/usr/bin/env bash
# Restore a gzipped SQLite backup. STOP THE BOT FIRST.
set -euo pipefail

BACKUP="${1:-}"
TARGET="${2:-data/community.db}"

if [[ -z "$BACKUP" || ! -f "$BACKUP" ]]; then
  echo "Usage: $0 <backup.db.gz> [target.db]" >&2
  exit 1
fi

if ! gzip -t "$BACKUP"; then
  echo "Backup is not a valid gzip file: $BACKUP" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -f "$TARGET" ]]; then
  PRE="$TARGET.pre-restore.$STAMP"
  mv "$TARGET" "$PRE"
  echo "Existing database moved to: $PRE"
fi
for sidecar in "$TARGET-wal" "$TARGET-shm"; do
  if [[ -f "$sidecar" ]]; then
    mv "$sidecar" "$sidecar.pre-restore.$STAMP"
    echo "Existing sidecar moved to: $sidecar.pre-restore.$STAMP"
  fi
done

TMP="$TARGET.restore.tmp"
gunzip -c "$BACKUP" > "$TMP"
python3 - "$TMP" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
try:
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise SystemExit(f"integrity check failed: {result}")
finally:
    conn.close()
PY
mv "$TMP" "$TARGET"
echo "Restored to: $TARGET"
echo "Start the bot, then check /readyz and !leaderboard."
