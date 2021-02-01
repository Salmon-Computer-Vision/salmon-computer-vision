#!/usr/bin/env bash

# Expects source_dir to have file paths
# ${source_dir}/
#   33/
#       dataset/
#       sources/
#   35/
#   <task_id>/
#   ...

user=$1
pass=$2 # Pass using env var
source_dir=$3
filtered_dir=$4
dest_dir=$5

exp_script="$(pwd)/script.exp"

for task in "${source_dir}"/*; do
    t_name=$(basename "$task")
    task_filt="$(pwd)/${filtered_dir}/${t_name}"

    if [ -d "${task}"/sources/*/images ]; then
       (cd "${task}"; datum export -o "${task_filt}" -e '/item/annotation' --filter-mode i+a -f datumaro -- --save-images)
    else
       (cd "${task}"; "${exp_script}" "${user}" "${pass}" "${task_filt}")
    fi

    datum import -i "${task_filt}" -o "${task_filt}" -f datumaro

    #(cd "${task}"; datum filter -e '/item/annotation' -m i+a -o "${task_filt}" --overwrite)
    datum transform -p "${task_filt}" -o "${task_filt}" -t rename --overwrite -- -e "|frame_(\d+)|${t_name}_\1|"
done

datum merge "${filtered_dir}"/* -o "${dest_dir}"

# Split training, validation, and test sets
datum transform -p "$dest_dir" -o "${dest_dir}_split" -t detection_split --overwrite -- -s train:.5 -s val:.2 -s test:.3

# Copy cvat REST plugin
#tasks=( "${source_dir}"/* )
#cp -r "${tasks[0]}/.datumaro/plugins" "${dest_dir}/.datumaro"
#
#for task in "${source_dir}"/*; do
#    t_name=$(basename "$task")
#    # Add sources from each task (Requires cvat folder in current directory)
#    datum source add path -p "${dest_dir}" -f cvat_rest_api_task_images -n "$t_name" "${task}"/sources/*
#done
