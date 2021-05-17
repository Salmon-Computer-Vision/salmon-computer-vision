#!/usr/bin/env bash

# Ex. ./make_cvat_tasks.sh ../../cvat/utils/cli/cli.py kami:${pass} 10.0.0.146 labels-converted.json ../../salmon-count-labels/annotation ~/gdrive

set -e

cli=$1
auth=$2 # username:pass-env
host=$3
labels=$4
anno_folder=$5
drive_folder=$6 # Assuming drive share is initialized with `drive init`

task_list=`"${cli}" --auth "${auth}" --server-host "${host}" ls`

new_tasks_list="new_created_tasks.txt"
echo '' > "$new_tasks_list"

# Hardcoded list name
salmon_list="${drive_folder}/salmon_list.txt"

for anno in "${anno_folder}"/*.zip; do
    tmp=`echo ${anno} | grep -oP '\d{2}-\d{2}-\d{4}_\d{2}.*(?=.zip)'`
    name=${tmp//_/ }

    [ -z "$name" ] && continue # If empty, skip

    drivepath=$(cat "${salmon_list}" | grep "${name}")
    [ -z "$drivepath" ] && continue
    drivepath="${drivepath/\//}" # Remove leading forward slash

    # Download video
    (cd "${drive_folder}" && drive pull -no-prompt "${drivepath}")

    filepath="${drive_folder}/${drivepath}"
    #filepath=`find "${drive_folder}/Kitwanga Fish Video" "${drive_folder}/Training dataset" -name "${name}*" | head -n 1`
    share_path=${filepath#${drive_folder}}

    filename=`basename "${filepath}"`
    filename=${filename%.*} # Remove extension

    if echo "${task_list}" | grep -q "${filename}"; then
        continue
    fi

    TMP=$(mktemp)
    "${cli}" --auth "${auth}" --server-host "${host}" \
        create --labels "${labels}" \
        --annotation_path "${anno}" \
        --annotation_format "CVAT 1.1" \
        "${filename}" \
        share "${share_path}" 2>&1 | tee $TMP

    # Delete video
    rm -v "$filepath"

    err_msg=$(cat $TMP)
    
    # Delete the task if there is an error
    if [ $? -ne 0 ] || [[ "$err_msg" == *"Error"* ]]; then
        task_id=`"${cli}" --auth "${auth}" --server-host "${host}" ls | grep -oP "\d+(?=,${filename})"`
        "${cli}" --auth "${auth}" --server-host "${host}" delete ${task_id}
    fi
    
    echo "$err_msg" | grep -oP "(?<=Created task ID: )[0-9]+" >> "$new_tasks_list"
done
