#!/usr/bin/env bash

# Parse options
while getopts "s:o:i:d:c:" opt; do
    case $opt in
        s) SITE_NAME="$OPTARG" ;;
        o) ORGID="$OPTARG" ;;
        i) DEVICE_ID="$OPTARG" ;;
        d) DRIVE="$OPTARG" ;;
        c) CONFIG="$OPTARG" ;;
        \?) echo "Invalid option -$OPTARG" >&2 ;;
    esac
done

# Check required arguments
if [ -z "$SITE_NAME" ] || [ -z "$ORGID" ] || [ -z "$DEVICE_ID" ] || [ -z "$DRIVE" ] || [ -z "$CONFIG" ]; then
    echo "Usage: $0 -s SITE_NAME -o ORGID -i DEVICE_ID -d DRIVE -c CONFIG"
    exit 1
fi

rclone copy \
    --include="${ORGID}/${SITE_NAME}/${DEVICE_ID}/logs/**" \
    --progress \
    -c "$CONFIG" \
    /media/local_hdd "${DRIVE}"

sleep 2h
