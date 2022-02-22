#!/usr/bin/env bash

# You must be in this folder to run this script

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path/to/logs_dir> <path/to/dest_dir>"
    echo "Converts all your JSON iperf logs to csv."
    exit 0
fi

logs_dir="$1"
dest_dir="$2"

for dir in "${logs_dir}"/*/; do 
    parallel python3 ./iperf-data-plot/main.py -o "${dest_dir}/$(basename $dir)" ::: "${dir}"/*.log
done
