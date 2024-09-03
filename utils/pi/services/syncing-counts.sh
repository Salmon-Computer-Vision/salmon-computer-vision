#!/usr/bin/env sh

# Function to perform rclone operations
rclone_copy() {
    site_name="$1"
    config="$2"
    src="$3"
    dst="$4"
    
    rclone copy --bwlimit=0 --buffer-size=128M --transfers=2 --include "/${site_name}/*/counts/**" \
        "$src" "$dst" --config "$config" --log-level INFO
}

# Function to concatenate CSV files in a directory
concatenate_csv_in_directory() {
    echo "Concatenating CSVs..."
    dir="$1"
    output_file="$2"
    first=1
    for file in "$dir"/*_M.csv; do
        if [ -f "$file" ]; then
            if [ "$first" -eq 1 ]; then
                cat "$file" > "$output_file"
                first=0
            else
                tail -n +2 "$file" >> "$output_file"
            fi
        fi
    done
}

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
REMOTE_PATH="aws:${BUCKET}/${ORGID}"
LOCAL_PATH="${DRIVE}/${ORGID}"

echo "Download from remote..."
rclone_copy "$SITE_NAME" "$CONFIG" "$REMOTE_PATH" "$LOCAL_PATH"

# Concatenate CSV files separately within each subfolder
for dir in "${LOCAL_PATH}/${SITE_NAME}"/*/counts; do
    if [ -d "$dir" ]; then
        parent_dir=$(dirname "$dir")
        base_dir=$(basename "$parent_dir")
        summary_csv_name="${ORGID}-${SITE_NAME}-${base_dir}_summary_salmon_counts.csv"
        output_file="${parent_dir}/${summary_csv_name}"
        concatenate_csv_in_directory "$dir" "$output_file"
        rclone copy "$output_file" "${REMOTE_PATH}/${SITE_NAME}/${base_dir}/" --config "$CONFIG" --log-level INFO
    fi
done

# Upload to remote
echo "Upload to remote..."
rclone_copy "$SITE_NAME" "$CONFIG" "$LOCAL_PATH" "$REMOTE_PATH"

echo "Finished. Waiting some time..."
sleep 30m
