#!/usr/bin/env bash

cli=$1
auth=$2 # username:pass-file
host=$3
labels=$4
anno_folder=$5
drive_share=$6

task_list=`"${cli}" --auth "${auth}" --server-host "${host}" ls`

for anno in "${anno_folder}"/*.zip; do
    tmp=`echo ${anno} | grep -oP '\d{2}-\d{2}-\d{4}_\d{2}-\d{2}-\d{2}'`
    name=${tmp//_/ }
    filepath=`find "${drive_share}/Kitwanga Fish Video" "${drive_share}/Training dataset" -name "${name}*"`
    share_path=${filepath#${drive_share}}

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

    err_msg=$(cat $TMP)
    
    # Delete the task if there is an error
    if [ $? -ne 0 ] || [[ "$err_msg" == *"Error"* ]]; then
        task_id=`"${cli}" --auth "${auth}" --server-host "${host}" ls | grep -oP "\d+(?=,${filename})"`
        "${cli}" --auth "${auth}" --server-host "${host}" delete ${task_id}
    fi
done
