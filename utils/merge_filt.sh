#!/usr/bin/env bash
set -e

# Requires datumaro and jq

# ./merge_filt.sh dump_filt merged

filtered_dir=$1
dest_dir=$2

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Update tracking ID(s) to be unique
#track_id=0
#for task in "${filtered_dir}"/*; do
#    echo "Task: $task"
#
#    anno_file="${task}"/annotations/default.json
#    temp_file=`mktemp` # jq cannot update in-place
#
#    jq --arg ID "$track_id" 'walk(if type == "object" and .track_id then .track_id += ($ID|tonumber) else . end)' "${anno_file}" > "$temp_file"
#
#    cp "$anno_file" "${anno_file}.back"
#    cp "$temp_file" "$anno_file"
#    rm "$temp_file"
#
#    # Get last tracking ID in case there were multiple tracks
#    track_id=$(jq -r '[..?|.track_id?] | max' "${anno_file}")
#    ((++track_id))
#
#    echo "Next Tracking ID: $track_id"
#done

datum merge "${filtered_dir}"/* -o "${dest_dir}"

split_dir="${dest_dir}_split"
# Split training, validation, and test sets
datum transform -p "$dest_dir" -o "$split_dir" -t random_split --overwrite -- -s train_1:.175 -s train_2:.175 -s train_3:.175 -s train_4:.175 -s val:.15 -s test:.15

"${SCRIPT_DIR}/sep_split.sh" "$split_dir"
