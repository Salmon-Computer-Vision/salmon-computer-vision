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
        f) FOLDER="$OPTARG" ;;
        t) TRANSFERS="$OPTARG" ;;
        \?) echo "Invalid option -$OPTARG" >&2 ;;
    esac
done

SITE_PATH="${DRIVE}/${ORGID}/${SITE_NAME}"

for device_path in "${SITE_PATH}"/* ; do
    if [ ! -d "$device_path" ]; then
        continue
    fi
    BACKUP="${device_path}/${FOLDER}_backup/"
    SRC="${device_path}/${FOLDER}/"
    DEST="aws:${BUCKET}/${ORGID}/${SITE_NAME}/${device_path##*/}/${FOLDER}/"

    mkdir -p "$BACKUP"
    mkdir -p "$SRC"
    #rclone copy "${device_path}/${FOLDER}/" "$BACKUP" \
    #    --transfers=8 \
    #    --progress

    rclone move "$SRC" "$DEST" \
        --bwlimit=0 \
        --buffer-size=128M \
        --transfers=8 \
        --min-age 30m \
        --config /config/rclone/rclone.conf \
        --log-level INFO \
        --s3-no-check-bucket
done

echo "Finished. Waiting some time..."
sleep 30m
