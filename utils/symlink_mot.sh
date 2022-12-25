#!/usr/bin/env bash
set -e

if [ "$#" -ne 2 ]; then
    echo "Enter args src and dest"
    exit 0
fi

src_path="$1"
dest_path="$2"

subsets=(train valid test)

for subset in ${subsets[@]}; do
    src_images_path="${src_path}/images/${subset}"
    dest_images_path="${dest_path}/images/${subset}"
    mkdir -p "$dest_images_path"

    for seq in "$src_images_path"/*; do
        ln -vs "$PWD/$seq" "$dest_images_path"
    done
done
