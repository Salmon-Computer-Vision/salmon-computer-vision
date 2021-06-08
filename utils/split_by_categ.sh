#!/usr/bin/env bash
set -e

dataset_dir=$1
label_file="$(pwd)/labels.txt"
cat_csv="$(pwd)/category_nums.csv"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path/to/dataset_dir>"
    echo "Counts the number of labeled frames for each label class"
    exit 0
fi

if [ ! -f "$label_file" ]; then
    jq -r '.[].name' labels-converted.json > "$label_file"
fi

echo "Species,Number" > "$cat_csv"
cd "${dataset_dir}"
while read label; do
    datum filter -e "/item[annotation/label=\"${label}\"]" -o "${label}" || true
    num=$(datum info -p "$label" | grep -oP -m1 '(?<=length: ).*' || true)
    if [ -z "$num" ]; then num=0; fi
    echo "${label},${num}" >> "$cat_csv"
done < "$label_file"
cd -
