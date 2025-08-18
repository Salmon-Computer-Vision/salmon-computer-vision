#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="/media/local_hdd"
DST_ROOT="/media/hdd"

# Safety check: destination must be mounted
if ! mountpoint -q "$DST_ROOT"; then
    echo "[$(date)] ERROR: $DST_ROOT is not mounted. Aborting move." >&2
    exit 1
fi

# Find log files older than 2 days and rsync them while preserving structure
cd "$SRC_ROOT"
find . -type f -name '*.txt' -mtime +2 -print0 \
  | rsync -av --remove-source-files --files-from=- --from0 . "$DST_ROOT"

