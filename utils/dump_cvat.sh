#!/usr/bin/env bash
# Will create annotation directories for each task at the destination folder

# TODO: Turn these into options
cli=$1
auth=$2 # username:pass-env
host=$3
start=$4
last=$5
dest_dir=$6

mkdir -p "$dest_dir"

tmp=$(mktemp)
"${cli}" --auth "${auth}" --server-host "${host}" ls > $tmp

task_list=$(cat $tmp)

for ((i=start; i<=last; i++)); do
    if ! (echo "${task_list}" | grep -e "^$i,"); then
        continue
    fi

    echo "Exporting task $i"

    task_dir="${dest_dir}/${i}"
    mkdir -p "$task_dir"

    "${cli}" --auth "${auth}" --server-host "${host}" \
        dump --format "Datumaro 1.0" $i "${task_dir}.zip"
    unzip "${task_dir}.zip" -d "$task_dir"
    rm -v "${task_dir}.zip"
done
