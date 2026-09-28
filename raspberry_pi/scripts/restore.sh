#!/bin/bash
# Restore a backup made by backup.sh (stops the services while restoring).
#   restore.sh /media/belt/USB/belt_marking_backup_YYYYmmdd_HHMMSS.tar.gz
set -euo pipefail
ARCHIVE="$1"
DATA="${BELT_DATA:-$HOME/.belt_marking}"
TMP=$(mktemp -d)
tar -xzf "$ARCHIVE" -C "$TMP"
DIR=$(find "$TMP" -maxdepth 1 -type d -name 'belt_marking_backup_*' | head -1)
sudo systemctl stop belt-marking-ui belt-marking-ros || true
mkdir -p "$DATA"
[ -f "$DATA/belt_marking.db" ] && mv "$DATA/belt_marking.db" "$DATA/belt_marking.db.before_restore"
rm -f "$DATA"/belt_marking.db-wal "$DATA"/belt_marking.db-shm
cp "$DIR/belt_marking.db" "$DATA/"
[ -f "$DIR/calibration.yaml" ] && cp "$DIR/calibration.yaml" "$DATA/"
[ -d "$DIR/etc_belt_marking" ] && sudo cp -a "$DIR/etc_belt_marking/." /etc/belt_marking/
rm -rf "$TMP"
sudo systemctl start belt-marking-ros belt-marking-ui
echo "restored from $ARCHIVE"
