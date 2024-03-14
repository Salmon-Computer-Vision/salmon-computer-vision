#!/usr/bin/env bash

# Check if an input argument (directory) is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory>"
    exit 1
fi

# Specify the base directory where the "train", "val", and "test" subfolders are located
base_dir="$1"

# List of subfolders to process
subfolders=("train" "val" "test")

# Iterate over each subfolder
for folder in "${subfolders[@]}"; do
    find "${base_dir}/${folder}" \( -name "*.png" -o -name "*.jpg" \) > "${base_dir}/${folder}.txt"
done

echo "Combination completed."

