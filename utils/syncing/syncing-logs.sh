#!/usr/bin/env sh
set -e

# Parse options
while getopts "s:b:o:d:c:t:" opt; do
    case $opt in
        s) SITE_NAME="$OPTARG" ;;
        b) BUCKET="$OPTARG" ;;
        o) ORGID="$OPTARG" ;;
        d) DRIVE="$OPTARG" ;;
        c) CONFIG="$OPTARG" ;;
        t) TRANSFERS="$OPTARG" ;;
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
    BACKUP="${device_path}/logs_backup/"
    SRC="${device_path}/logs/"
    DEST="aws:${BUCKET}/${ORGID}/${SITE_NAME}/${device_path##*/}/logs/"

    mkdir -p "$BACKUP"
    mkdir -p "$SRC"
    rclone copy "$SRC" "$BACKUP" \
        --transfers=8 \
        --no-traverse \
        --progress

    rclone move "$SRC" "$DEST" \
        --bwlimit=0 \
        --buffer-size=128M \
        --transfers=$TRANSFERS \
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
