#!/usr/bin/env bash
set -e

dataset_dir="$1" # YOLO dataset dir with multiple video frames
dest_dir="$2"

if [ $# -ne 2 ]; then
    echo "Usage: $0 <path/to/dataset_dir> <path/to/dest_dir>"
    echo "Converts yolo frames dataset to CVAT"
    exit 1
fi

mkdir -p "$dest_dir"
# Iterate subfolders only (Should only have video frames)
for vid_frames in "${dataset_dir}/"*/ ; do
    vid_frames="${dataset_dir}/08-01-2021_19-32-29_M_Salmon_Camera"
    echo "$vid_frames"
    # Find all images in folder
    find "$(cd $vid_frames; pwd)" -name '*.jpg' | sort > "${dataset_dir}/bear_creek_salmon.txt"
    dest_cvat="${dest_dir}/${vid_frames##${dataset_dir}/}"
    echo $dest_cvat
    datum convert -i "$dataset_dir" -if yolo -f cvat -o "$dest_cvat" --overwrite
done
