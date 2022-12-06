#!/usr/bin/env bash
set -e

train_split_dir="$1"
export_dir="$2"

subsets=(test valid train)
for subset in ${subsets[@]}; do
    subset_path="${train_split_dir}/${subset}"
    for d in "$subset_path"/*; do
        dest_dir="${export_dir}/${subset}/${d##*/}"
        if [ $(find "${export_dir}" -name "${d##*/}" | wc -l) = 2 ]; then
            echo Duplicate at ${d##*/}
            rm -r "$dest_dir"
        fi
        if [ ! -d "$dest_dir" ]; then
            mv -v $(find "${export_dir}" -name "${d##*/}") "${export_dir}/${subset}"
        fi
    done
done
