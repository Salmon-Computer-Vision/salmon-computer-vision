#!/usr/bin/env bash
set -euo pipefail

NO_BACKUP="false"
MIN_FREE_GB="50"

usage() {
    echo "Usage: $0 -s SITE_NAME -b BUCKET -o ORGID -d DRIVE -c CONFIG [-f MIN_FREE_GB] [-n]"
    echo "  -f MIN_FREE_GB  Minimum free space to maintain on DRIVE before backup/upload. Default: 50"
    echo "  -n              Do not create local backups before uploading"
}

# Parse options
while getopts "s:b:o:d:c:f:n" opt; do
    case $opt in
        s) SITE_NAME="$OPTARG" ;;
        b) BUCKET="$OPTARG" ;;
        o) ORGID="$OPTARG" ;;
        d) DRIVE="$OPTARG" ;;
        c) CONFIG="$OPTARG" ;;
        f) MIN_FREE_GB="$OPTARG" ;;
        n) NO_BACKUP="true" ;;
        \?) echo "Invalid option -$OPTARG" >&2; usage; exit 1 ;;
    esac
done

# Check required arguments
if [ -z "${SITE_NAME:-}" ] || [ -z "${BUCKET:-}" ] || [ -z "${ORGID:-}" ] || [ -z "${DRIVE:-}" ] || [ -z "${CONFIG:-}" ]; then
    usage
    exit 1
fi

if ! [[ "$MIN_FREE_GB" =~ ^[0-9]+$ ]]; then
    echo "MIN_FREE_GB must be a non-negative integer, got: $MIN_FREE_GB" >&2
    exit 1
fi

if [ ! -d "$DRIVE" ]; then
    echo "DRIVE does not exist or is not a directory: $DRIVE" >&2
    exit 1
fi

SITE_PATH="${DRIVE}/${ORGID}/${SITE_NAME}"
MIN_FREE_KIB=$((MIN_FREE_GB * 1024 * 1024))

get_free_kib() {
    local path="$1"
    df -Pk "$path" | awk 'NR == 2 {print $4}'
}

human_gib_from_kib() {
    local kib="$1"
    awk -v kib="$kib" 'BEGIN {printf "%.2f", kib / 1024 / 1024}'
}

delete_matching_backup_metadata() {
    local video_path="$1"
    local backup_dir device_dir stem meta_path

    backup_dir="$(dirname "$video_path")"
    device_dir="$(dirname "$backup_dir")"
    stem="$(basename "$video_path")"
    stem="${stem%.*}"
    meta_path="${device_dir}/motion_vids_metadata_backup/${stem}.json"

    if [ -f "$meta_path" ]; then
        echo "[CLEANUP] deleting matching metadata backup: $meta_path"
        rm -f -- "$meta_path"
    fi
}

ensure_min_free_space() {
    local target_path="$1"
    local cleanup_root="$2"
    local free_kib free_gib deleted entry backup_file

    free_kib="$(get_free_kib "$target_path")"
    free_gib="$(human_gib_from_kib "$free_kib")"

    if (( free_kib >= MIN_FREE_KIB )); then
        echo "[SPACE] ${target_path}: ${free_gib} GiB free; threshold=${MIN_FREE_GB} GiB"
        return 0
    fi

    echo "[SPACE] ${target_path}: only ${free_gib} GiB free; deleting oldest backup clips until >= ${MIN_FREE_GB} GiB" >&2

    if [ ! -d "$cleanup_root" ]; then
        echo "[ERROR] Cleanup root does not exist: $cleanup_root" >&2
        exit 1
    fi

    deleted=0

    # Delete only source backups, never active motion_vids. The matching JSON
    # metadata backup is removed beside each deleted video when it exists.
    while IFS= read -r -d '' entry; do
        free_kib="$(get_free_kib "$target_path")"
        if (( free_kib >= MIN_FREE_KIB )); then
            break
        fi

        backup_file="${entry#* }"
        if [ ! -f "$backup_file" ]; then
            continue
        fi

        echo "[CLEANUP] deleting oldest backup clip: $backup_file"
        rm -f -- "$backup_file"
        delete_matching_backup_metadata "$backup_file"
        deleted=$((deleted + 1))
    done < <(
        find "$cleanup_root" \
            -type f \
            -path '*/motion_vids_backup/*' \
            \( -iname '*.mp4' -o -iname '*.m4v' -o -iname '*.mov' -o -iname '*.avi' \) \
            -printf '%T@ %p\0' \
        | sort -z -n
    )

    free_kib="$(get_free_kib "$target_path")"
    free_gib="$(human_gib_from_kib "$free_kib")"

    if (( free_kib < MIN_FREE_KIB )); then
        echo "[ERROR] Still below free-space threshold after deleting ${deleted} backup clips: ${free_gib} GiB free < ${MIN_FREE_GB} GiB required" >&2
        exit 1
    fi

    echo "[SPACE] cleanup complete: deleted=${deleted}; ${free_gib} GiB free"
}

for device_path in "${SITE_PATH}"/* ; do
    if [ ! -d "$device_path" ]; then
        continue
    fi

    BACKUP="${device_path}/motion_vids_backup/"
    BACKUP_META="${device_path}/motion_vids_metadata_backup/"
    SRC="${device_path}/motion_vids/"
    SRC_META="${device_path}/motion_vids_metadata/"
    DEST="aws:${BUCKET}/${ORGID}/${SITE_NAME}/${device_path##*/}/"

    mkdir -p "$SRC"
    mkdir -p "$SRC_META"
    mkdir -p "$BACKUP"
    mkdir -p "$BACKUP_META"

    # Check the target drive before creating more backup data. This cleanup is
    # global for the site path so older backups from any device can be reclaimed.
    ensure_min_free_space "$DRIVE" "$SITE_PATH"

    if [[ "$NO_BACKUP" != "true" ]]; then
        rclone copy "$SRC" "$BACKUP" \
            --transfers=2 \
            --no-traverse \
            --progress

        rclone copy "$SRC_META" "$BACKUP_META" \
            --transfers=8 \
            --no-traverse \
            --progress
    fi

    rclone move "$device_path" "$DEST" \
        --include "/motion_vids/**" \
        --include "/motion_vids_metadata/**" \
        --bwlimit=0 \
        --buffer-size=128M \
        --transfers=2 \
        --min-age 30m \
        --no-traverse \
        --config "$CONFIG" \
        --log-level INFO \
        --s3-no-check-bucket
done

echo "Finished. Waiting some time..."
sleep 30m
