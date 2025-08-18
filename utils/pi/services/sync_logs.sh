#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="/media/local_hdd"
DST_ROOT="/media/hdd"

# Safety check: destination must be mounted
if ! mountpoint -q "$DST_ROOT"; then
    echo "[$(date)] ERROR: $DST_ROOT is not mounted. Aborting sync." >&2
    exit 1
fi

# Sync all logs while preserving structure
rsync -av \
  --include='*/' \
  --include='*.txt' \
  --exclude='*' \
  "$SRC_ROOT" "$DST_ROOT"
