#!/usr/bin/env bash

# Creates new CVAT tasks for the videos at the share folder

set -e

show_help() {
    echo "$0 [-c path/to/cvat/utils/cli/cli.py] [-n localhost] user:pass labels.json path/to/share_folder path/to/vid_folder"
}

OPTIND=1 # Reset in case getopts has been used previously in the shell.

cli="../../cvat/utils/cli/cli.py"
host="localhost"

while getopts "h?c:n:" opt; do
   case "$opt" in
      h|\?) # display Help
         show_help
         exit 0
         ;;
     c) # Set cli.py path
         cli=$OPTARG
         ;;
     n) # Hostname
         host=$OPTARG
         ;;
   esac
done

shift $((OPTIND-1))

if [ "$#" -lt 4 ]; then
    echo "Insufficient number of arguments"
    show_help
    exit 1
fi

auth=$1 # username:pass-env
labels=$2 # Labels.json path
share_folder=$3 # Share folder specified on CVAT
vid_folder=$4 # Videos folder within share folder

task_list=`"${cli}" --auth "${auth}" --server-host "${host}" ls`

for vid in "$vid_path"/*; do
    name=`basename "${vid%.*}"` # Remove file extension and get basename

    if [ -z "$name" ]; then
        echo "Skipping empty name"
        continue
    fi

    if echo "${task_list}" | grep -q "${name}"; then
        echo "Task already exists. Skipping ${name}"
        continue
    fi

    share_path=${vid#${share_folder}}

    TMP=$(mktemp)
    "${cli}" --auth "${auth}" --server-host "${host}" \
        create --labels "${labels}" \
        "${name}" \
        share "${share_path}" 2>&1 | tee $TMP

    err_msg=$(cat $TMP)
    
    # Delete the task if there is an error
    if [ $? -ne 0 ] || [[ "$err_msg" == *"Error"* ]]; then
        task_id=`"${cli}" --auth "${auth}" --server-host "${host}" ls | grep -oP "\d+(?=,${filename})"`
        "${cli}" --auth "${auth}" --server-host "${host}" delete ${task_id}
    else
        echo "$err_msg" | grep -oP "(?<=Created task ID: )[0-9]+" >> "$new_tasks_list"
    fi
done
