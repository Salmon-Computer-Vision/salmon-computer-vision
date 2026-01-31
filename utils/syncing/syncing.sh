#!/usr/bin/env sh
set -e

# Parse options
while getopts "s:b:o:d:c:" opt; do
    case $opt in
        s) SITE_NAME="$OPTARG" ;;
        b) BUCKET="$OPTARG" ;;
        o) ORGID="$OPTARG" ;;
        d) DRIVE="$OPTARG" ;;
        c) CONFIG="$OPTARG" ;;
        \?) echo "Invalid option -$OPTARG" >&2 ;;
    esac
done

# Check required arguments
if [ -z "$SITE_NAME" ] || [ -z "$BUCKET" ] || [ -z "$ORGID" ] || [ -z "$DRIVE" ] || [ -z "$CONFIG" ]; then
    echo "Usage: $0 -s SITE_NAME -b BUCKET -o ORGID -d DRIVE -c CONFIG"
    exit 1
fi

SITE_PATH="${DRIVE}/${ORGID}/${SITE_NAME}"

for device_path in "${SITE_PATH}"/* ; do
    if [ ! -d "$device_path" ]; then
        continue
    fi
    BACKUP="${device_path}/motion_vids_backup/"
    BACKUP_META="${device_path}/motion_vids_metadata_backup/"
    SRC="${device_path}/motion_vids/"
    SRC_META="${device_path}/motion_vids_metadata/"
    DEST="aws:${BUCKET}/${ORGID}/${SITE_NAME}/${device_path##*/}/"

    mkdir -p "$BACKUP"
    mkdir -p "$BACKUP_META"
    rclone copy "$SRC" "$BACKUP" \
        --transfers=2 \
        --no-traverse \
        --progress

    rclone copy "$SRC_META" "$BACKUP_META" \
        --transfers=8 \
        --no-traverse \
        --progress

    rclone move "$device_path" "$DEST" \
        --include "/motion_vids/**" \
        --include "/motion_vids_metadata/**" \
        --bwlimit=0 \
        --buffer-size=128M \
        --transfers=2 \
        --min-age 30m \
        --no-traverse \
        --delete-empty-src-dirs \
        --config /config/rclone/rclone.conf \
        --log-level INFO \
        --s3-no-check-bucket
done

echo "Finished. Waiting some time..."
sleep 30m

