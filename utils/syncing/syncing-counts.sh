#!/usr/bin/env sh

# Function to perform rclone operations
rclone_copy() {
    site_name="$1"
    config="$2"
    include="$3"
    src="$4"
    dst="$5"
    
    rclone copy --bwlimit=0 --buffer-size=128M --transfers=2 --include "$include" \
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

# Upload to remote
echo "Upload to remote..."
rclone_copy "$SITE_NAME" "$CONFIG" "/${SITE_NAME}/*/counts/**" "$LOCAL_PATH" "$REMOTE_PATH"

echo "Finished. Waiting some time..."
sleep 30m
