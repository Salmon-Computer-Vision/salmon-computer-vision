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

if [ "$#" -le 4 ]; then
    echo "Must have at least 4 parameters"
fi

user=$1
pass=$2 # Pass using env var
source_dir=$3
filtered_dir=$4

# XPath to filter every other frame
# /item[number(substring(/item/id, 7)) mod 2 = 0]
xpath_filt='/item'
if [ "$#" -eq 5 ]; then
    xpath_filt=$5
fi

echo $xpath_filt

track_idx=0

exp_script="$(pwd)/script.exp"

# Must export PYTHONPATH to find cvat module
PYTHONPATH=':'
export PYTHONPATH

for task in "${source_dir}"/*; do
    t_name=$(basename "$task")
    task_filt="${filtered_dir}/${t_name}"

   (cd "${task}"; "${exp_script}" "${user}" "${pass}" "${task_filt}" "${xpath_filt}")

    if [ ! -f "${task_filt}/annotations/default.json" ]; then
        rm -rv "${task_filt}"
        continue
    fi

    datum import -i "${task_filt}" -o "${task_filt}" -f datumaro --overwrite

    #(cd "${task}"; datum filter -e '/item/annotation' -m i+a -o "${task_filt}" --overwrite)
    datum transform -p "${task_filt}" -o "${task_filt}" -t rename --overwrite -- -e "|frame_(\d+)|${t_name}_\1|"
done
