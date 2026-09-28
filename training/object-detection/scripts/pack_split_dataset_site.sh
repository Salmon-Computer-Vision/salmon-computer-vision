#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 <site> <dataset-root> <bucket> <download-workers>" >&2
    exit 2
fi

SITE="$1"
DATASET_ROOT="$2"
BUCKET="$3"
DOWNLOAD_WORKERS="$4"

BASE="${DATASET_ROOT}/salmon_dataset"

TMP_LABELS="${BASE}/tmp_labels/${SITE}"
TMP_PACK="${BASE}/tmp_pack/${SITE}"
RETRY_CACHE="${BASE}/pack_retry_cache/${SITE}"

SITE_DATASET="${BASE}/dataset_sharded/sites/${SITE}"
LEGACY_SHARDS="${BASE}/dataset_sharded/shards"

echo "[pack] Site: ${SITE}"
echo "[pack] Dataset root: ${DATASET_ROOT}"

#
# ---------------------------------------------------------------------------
# Prepare retry cache
# ---------------------------------------------------------------------------
#
# If tmp_pack contains a completed previous attempt, preserve it as the
# highest-priority frame cache for this run.
#
# Important:
#   Do NOT delete an existing retry cache unless we have a completed tmp_pack
#   to replace it with. This protects the retry cache if an earlier attempt
#   was interrupted halfway through.
#

mkdir -p \
    "${BASE}/tmp_labels" \
    "${BASE}/tmp_pack" \
    "${BASE}/pack_retry_cache"

rm -rf "${TMP_LABELS}"

if [[ -f "${TMP_PACK}/packed_dataset_manifest.csv" ]]; then
    echo "[pack] Previous completed failed attempt found."
    echo "[pack] Moving it into retry cache: ${RETRY_CACHE}"

    rm -rf "${RETRY_CACHE}"
    mv "${TMP_PACK}" "${RETRY_CACHE}"

elif [[ -e "${TMP_PACK}" ]]; then
    echo "[pack] Removing incomplete tmp_pack from interrupted attempt:"
    echo "[pack]   ${TMP_PACK}"

    rm -rf "${TMP_PACK}"
fi

mkdir -p "${TMP_LABELS}"
mkdir -p "${TMP_PACK}"

#
# ---------------------------------------------------------------------------
# Unpack current labels
# ---------------------------------------------------------------------------
#

echo "[pack] Unpacking annotations..."

scripts/unpack_annos.sh \
    "data/02_interim/sites/${SITE}/yolo_annos" \
    "${TMP_LABELS}"

scripts/unpack_annos.sh \
    "data/02_interim/yolo_condition_negatives" \
    "${TMP_LABELS}"

#
# ---------------------------------------------------------------------------
# Pack dataset
# ---------------------------------------------------------------------------
#
# Cache priority:
#
#   1. previous failed attempt
#   2. previous successful per-site dataset
#   3. legacy combined dataset
#   4. source MP4 from S3
#
# pack_split_dataset.py intentionally exits non-zero after processing all
# videos if any video failed. Because set -e is active, execution stops here
# on that failure and TMP_PACK remains available for the next attempt.
#

echo "[pack] Packing dataset..."

scripts/pack_split_dataset.py \
    --splits-dir \
        "data/03_processed/sites/${SITE}/splits_baseline" \
    --labels-root \
        "${TMP_LABELS}" \
    --shards-root \
        "${TMP_PACK}/shards" \
    --manifests-root \
        "${TMP_PACK}/manifests" \
    --temp-video-dir \
        "${BASE}/tmp_videos/${SITE}" \
    --metadata-csv \
        "data/02_interim/sites/${SITE}/video_metadata_index.csv" \
        "data/02_interim/yolo_condition_negatives/condition_negative_video_metadata.csv" \
    --reuse-shards-root \
        "${RETRY_CACHE}/shards" \
    --reuse-shards-root \
        "${SITE_DATASET}/shards" \
    --reuse-shards-root \
        "${LEGACY_SHARDS}" \
    --data-yaml \
        "config/salmon_yolo.yaml" \
    --bucket \
        "${BUCKET}" \
    --image-ext \
        ".jpg" \
    --manifest-csv \
        "${TMP_PACK}/packed_dataset_manifest.csv" \
    --splits \
        train val test \
    --shard-size \
        100000 \
    --download-workers \
        "${DOWNLOAD_WORKERS}"

#
# ---------------------------------------------------------------------------
# Commit successful result
# ---------------------------------------------------------------------------
#
# We only reach here when pack_split_dataset.py returns 0, meaning no videos
# failed.
#

echo "[pack] Packing succeeded for ${SITE}."
echo "[pack] Committing new site dataset..."

rm -rf "${SITE_DATASET}"
mv "${TMP_PACK}" "${SITE_DATASET}"

#
# The retry cache is no longer necessary because SITE_DATASET now contains
# every successfully packed frame.
#

rm -rf "${RETRY_CACHE}"
rm -rf "${TMP_LABELS}"

echo "[pack] Completed successfully: ${SITE}"
