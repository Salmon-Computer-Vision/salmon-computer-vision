#!/usr/bin/env bash

# Ex. ./make_cvat_tasks.sh ../../cvat/utils/cli/cli.py kami:${pass} 10.0.0.146 labels-converted.json ../../salmon-count-labels/annotation ~/gdrive

set -e

show_help() {
    echo "$0 [-l] path/to/cli.py user:pass localhost labels.json path/to/annotations path/to/drive"
}

OPTIND=1 # Reset in case getopts has been used previously in the shell.

while getopts "h?l" opt; do
   case "$opt" in
      h|\?) # display Help
         show_help
         exit 0
         ;;
     s) # Set local to true, treats drive folder as local share folder
         local=true
         ;;
   esac
done

shift $((OPTIND-1))

if [ "$#" -lt 6 ]; then
    echo "Insufficient number of arguments"
    show_help
    exit 1
fi

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
    tmp=`echo ${anno} | grep -oP '\d{2,4}-\d{2,4}-\d{2,4}.*(?=.zip)'`
    name=${tmp//_/ }

    if [ -z "$name" ]; then
        echo "Skipping empty name"
        continue # If empty, skip
    fi

    if echo "${task_list}" | grep -q "${name}"; then
        echo "Task already exists. Skipping ${name}"
        continue
    fi

    if [ "$local" = true ]; then
        filepath=`find "${share_folder}" -name "${name}*" | head -n 1`
    else
        drivepath=$(cat "${salmon_list}" | grep -m1 "${name}" || true) # -m1 to get first video path if multiple
        if [ -z "$drivepath" ]; then
            echo "Video not found gdrive. Skipping ${name}"
            continue
        fi
        drivepath="${drivepath/\//}" # Remove leading forward slash

        # Download video
        if ! (cd "${drive_folder}" && drive pull -no-prompt "${drivepath}"); then
            echo "Failed drive pull, sleeping for a minute before trying again"
            sleep 1m
            (cd "${drive_folder}" && drive pull -no-prompt "${drivepath}")
        fi
        filepath="${drive_folder}/${drivepath}"

        share_folder="${drive_folder}"
    fi

    share_path=${filepath#${share_folder}}

    filename=`basename "${filepath}"`
    filename=${filename%.*} # Remove extension

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
    else
        echo "$err_msg" | grep -oP "(?<=Created task ID: )[0-9]+" >> "$new_tasks_list"
    fi
done
