#!/usr/bin/env bash
set -e

# ./merge_datum.sh dump_filt merged

filtered_dir=$1
dest_dir=$2

# Update tracking ID(s) to be unique
track_id=0
for task in "${filtered_dir}"/*; do
    anno_file="${task}"/annotations/default.json
    jq --arg ID "$track_id" 'walk(if type == "object" and .track_id then .track_id += ($ID|tonumber) else . end)' "${anno_file}" > "${anno_file}"

    # Get last tracking ID
    track_id=$(jq '[..?|.track_id?] | max' "${anno_file}")
    ((track_id++))
done

datum merge "${filtered_dir}"/* -o "${dest_dir}"

# Split training, validation, and test sets
datum transform -p "$dest_dir" -o "${dest_dir}_split" -t detection_split --overwrite -- -s train_1:.175 -s train_2:.175 -s train_3:.175 -s train_4:.175 -s val:.15 -s test:.15
