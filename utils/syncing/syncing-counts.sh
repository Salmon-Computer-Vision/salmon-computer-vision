#!/usr/bin/env sh

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

# Define paths
SITE_PATH="${DRIVE}/${ORGID}/${SITE_NAME}"

for device_path in "${SITE_PATH}"/* ; do
    if [ ! -d "$device_path" ]; then
        continue
    fi
    BACKUP="${device_path}/counts_backup/"
    src="${device_path}/counts"
    DEST="aws:${BUCKET}/${ORGID}/${SITE_NAME}/${device_path##*/}/counts"

    mkdir -p "$BACKUP"
    mkdir -p "$SRC"
    rclone copy "$SRC" "$BACKUP" \
        --transfers=8 \
        --no-traverse \
        --progress

    # Upload to remote
    echo "Upload to remote..."
    rclone move "$SRC" "$DEST" \
        --bwlimit=0 \
        --buffer-size=128M \
        --transfers=2 \
        --checkers 16 \
        --min-age 30m \
        --no-traverse \
        --delete-empty-src-dirs \
        --config /config/rclone/rclone.conf \
        --log-level WARNING \
        --stats 60s \
        --stats-one-line \
        --s3-no-check-bucket
done

echo "Finished. Waiting some time..."
sleep 30m
