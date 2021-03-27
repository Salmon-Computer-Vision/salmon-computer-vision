#!/bin/local/env bash

# ./merge_datum.sh dump_filt merged

filtered_dir=$1
dest_dir=$2

    # Update tracking ID(s)
    #jq 'walk(if type == "object" and .track_id then .track_id += 1 else . end)' "${

datum merge "${filtered_dir}"/* -o "${dest_dir}"

# Split training, validation, and test sets
datum transform -p "$dest_dir" -o "${dest_dir}_split" -t detection_split --overwrite -- -s train_1:.175 -s train_2:.175 -s train_3:.175 -s train_4:.175 -s val:.15 -s test:.15
