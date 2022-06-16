#!/usr/bin/env bash

# You must be in this folder to run this script

if [ $# -ne 2 ]; then
    echo "Usage: $0 <path/to/logs_dir> <path/to/dest_dir>"
    echo "Converts all your JSON iperf logs to csv."
    exit 0
fi

logs_dir="$1"
dest_dir="$2"

IFS=$'\n'
for dir in $(find "${logs_dir}" -type d); do 
    if compgen -G "${dir}"/*.log > /dev/null && [ "$logs_dir" != "$dir" ]; then
        new_path="${dir#"$logs_dir"}"
        parallel python3 ./iperf-data-plot/main.py -o "${dest_dir}/${new_path}" ::: "${dir}"/*.log
    fi 
done
