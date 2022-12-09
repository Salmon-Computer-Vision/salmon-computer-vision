#!/usr/bin/env bash
# Symlink YOLOv5 dataset into a YOLOv6 formatted dataset

src_path="$1"
dest_path="$2"

subsets=(train valid test)

for subset in ${subsets[@]}; do
    images_path="${dest_path}/images/${subset}"
    labels_path="${dest_path}/labels/${subset}"
    mkdir -p "${images_path}" "${labels_path}"
    while read -r img_path; do
        name=$(basename -- "$img_path")
        parent_path=$(dirname $(dirname "$img_path"))
        seq=$(basename "$parent_path")

        ln -vs "${img_path}" "${images_path}/${seq}_${name}"
        ln -s "${img_path%.*}.txt" "${labels_path}/${seq}_${name%.*}.txt"
    done < "${src_path}/${subset}.txt"
done
