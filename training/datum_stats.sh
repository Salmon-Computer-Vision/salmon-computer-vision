#!/usr/bin/env bash

# Check if an input argument (directory) is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory>"
    exit 1
fi

input_dir="$1"

i=0
find "$input_dir" -type f -name 'default.json' -exec dirname {} \; | uniq | while read subdir; do
    (
    mkdir $i
    cd $i
    datum stats --image-stats False "$(dirname "$subdir")" &
    )
    ((i=i+1))
done
