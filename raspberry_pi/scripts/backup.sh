#!/bin/bash
# Back up recipes, production DB, calibration and site config to a USB stick (or a dir).
#   backup.sh [target_dir]      default: first mounted USB stick, else ~/belt_marking_backups
set -euo pipefail
DATA="${BELT_DATA:-$HOME/.belt_marking}"
TARGET="${1:-$(ls -d /media/$USER/* 2>/dev/null | head -1)}"
TARGET="${TARGET:-$HOME/belt_marking_backups}"
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$TARGET/belt_marking_backup_$STAMP"
mkdir -p "$OUT"
# consistent online copy of the SQLite DB (WAL-safe)
python3 - "$DATA/belt_marking.db" "$OUT/belt_marking.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
cp -a "$DATA/calibration.yaml" "$OUT/" 2>/dev/null || true
cp -a /etc/belt_marking "$OUT/etc_belt_marking" 2>/dev/null || true
tar -czf "$OUT.tar.gz" -C "$TARGET" "$(basename "$OUT")" && rm -rf "$OUT"
sync
echo "backup written: $OUT.tar.gz"
