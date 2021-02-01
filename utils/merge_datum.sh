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

    #export_cmd=


    #if [ -d "${task}/sources/*/images" ]; then
    #    (cd "${task}"; datum export -o . -e '/item/annotation' --filter-mode i+a -f datumaro --overwrite -- --save-images)
    #else
    #    (cd "${task}"; "${exp_script}" "${user}" "${pass}" ".")
    #fi


    #datum import -i "${task}" -o "${task}" -f datumaro --overwrite

    (cd "${task}"; datum filter -e '/item/annotation' -m i+a -o "${task_filt}")
    datum transform -p "${task}" -o "${task_filt}" -t rename --overwrite -- -e "|frame_(\d+)|${t_name}_\1|"
done

datum merge "${filtered_dir}"/* -o "${dest_dir}"
# Split training, validation, and test sets

# Copy cvat REST plugin
tasks=( "${source_dir}"/* )
cp -r "${tasks[0]}/.datumaro/plugins" "${dest_dir}/.datumaro"

for task in "${source_dir}"/*; do
    t_name=$(basename "$task")
    # Add sources from each task (Requires cvat folder in current directory)
    datum source add path -p "${dest_dir}" -f cvat_rest_api_task_images -n "$t_name" "${task}"/sources/*
done
