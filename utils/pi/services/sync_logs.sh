#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="/media/local_hdd/"
DST_ROOT="/media/hdd/"

# Sync all logs while preserving structure
rsync -av \
  --include='*/' \
  --include='logs/**' \
  --exclude='*' \
  "$SRC_ROOT" "$DST_ROOT"
