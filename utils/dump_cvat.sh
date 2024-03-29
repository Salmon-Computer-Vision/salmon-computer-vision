#!/usr/bin/env bash
# Will create annotation directories for each task at the destination folder
# Good to have an empty destination folder
# This will NOT overwrite existing files

# Ex. ./dump_cvat.sh ../../cvat/utils/cli/cli.py kami:${pass} localhost 160 460 dump
# Dump annos to upload to github Ex. ./dump_cvat.sh -cf "CVAT for video 1.1" ../../cvat/utils/cli/cli.py kami:${pass} 10.0.0.146 1116 1117 dump_anno


show_help() {
    echo './dump_cvat.sh [-hnc] [-f "format"] path/to/cli.py user:${pass} localhost num_init num_end path/to/dump/dest'
}

OPTIND=1 # Reset in case getopts has been used previously in the shell.

format="Datumaro 1.0"
unzip=true
change_name_xml=false
error_list_file=dump_cvat_errored.txt
echo '' > $error_list_file

while getopts "h?f:nc" opt; do
   case "$opt" in
      h|\?) # display Help
         show_help
         exit 0
         ;;
      f) # Enter a name
         format=$OPTARG
         ;;
     n) # Do not unzip
         unzip=false
         ;;
     c) # Change the name of the .zip using the name inside the CVAT XML annotations
         change_name_xml=true
         ;;
   esac
done

shift $((OPTIND-1))

# TODO: Turn these into options
cli=$1
auth=$2 # username:pass-env
host=$3
start_id=$4
last_id=$5
dest_dir=$6

mkdir -p "$dest_dir"

tmp=$(mktemp)
"${cli}" --auth "${auth}" --server-host "${host}" ls > $tmp

task_list=$(cat $tmp)


for ((i=start_id; i<=last_id; i++)); do
    if ! (echo "${task_list}" | grep -qe "^$i,"); then
        continue
    fi

    echo "Exporting task $i"

    task_dir="${dest_dir}/${i}"

    RETRY_LIMIT=3
    count=0
    while [ true ]; do
        "${cli}" --auth "${auth}" --server-host "${host}" \
            dump --format "$format" $i "${task_dir}.zip"
        ret_code=$?

        if [[ $ret_code -ne 0 ]]; then
            if [[ "$count" -ge "$RETRY_LIMIT" ]]; then
                echo Skipping task due to excessive errors
                break
            fi
            (( count++ ))
            sleep 10
        else
            if [ "$unzip" = true ]; then mkdir -p "$task_dir"; fi
            break
        fi
    done

    if [ "$unzip" = true ] || [ "$change_name_xml" = true ]; then
        unzip -qn "${task_dir}.zip" -d "$task_dir"

        if [ "$change_name_xml" = true ]; then
            name=$(xpath -q -e '//task/name/text()' ${task_dir}/annotations.xml) # Specifically CVAT for videos 1.1
            mv -v "${task_dir}.zip" "${dest_dir}/${name%.*}.zip"
        else
            if ! rm -v "${task_dir}.zip"; then
                echo $i >> $error_list_file
            fi
        fi
    fi

    sleep 0.2
done
