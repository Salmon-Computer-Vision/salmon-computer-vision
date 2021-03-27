#!/usr/bin/env bash
set -e

# Expects source_dir to have file paths
# ${source_dir}/
#   33/
#       dataset/
#       sources/
#   35/
#   <task_id>/
#   ...

# Ex. ./download_frames.sh kami "${pass}" dump dump_filt

user=$1
pass=$2 # Pass using env var
source_dir=$3
filtered_dir=$4

track_idx=0

exp_script="$(pwd)/script.exp"

# Must export PYTHONPATH to find cvat module
PYTHONPATH=':'
export PYTHONPATH

for task in "${source_dir}"/*; do
    t_name=$(basename "$task")
    task_filt="${filtered_dir}/${t_name}"

    if [ -d "${task}"/sources/*/images ]; then
       (cd "${task}"; datum export --overwrite -o "${task_filt}" -e '/item/annotation' --filter-mode i+a -f datumaro -- --save-images)
    else
       (cd "${task}"; "${exp_script}" "${user}" "${pass}" "${task_filt}")
    fi

    datum import -i "${task_filt}" -o "${task_filt}" -f datumaro --overwrite

    #(cd "${task}"; datum filter -e '/item/annotation' -m i+a -o "${task_filt}" --overwrite)
    datum transform -p "${task_filt}" -o "${task_filt}" -t rename --overwrite -- -e "|frame_(\d+)|${t_name}_\1|"
done
