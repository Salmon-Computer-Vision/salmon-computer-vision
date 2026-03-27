#!/usr/bin/env bash
set -e

help_msg() {
    echo "$0 [-h] in_folder out_folder"
}

# Get the options
while getopts ":h" option; do
    case $option in
        h) # display Help
            help_msg
            exit;;
        \?) # Invalid option
            echo "Error: Invalid option"
            help_msg
            exit;;
    esac
done

# Check if exactly two arguments are given
if [ $# -ne 2 ]; then
    help_msg
    exit 1
fi

in_path="$1"
out_path="$2"

mkdir -p "$out_path"
for f in "$in_path"/*.tar; do
    tar -xf "$f" -C "$out_path"
done
