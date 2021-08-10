#!/usr/bin/env bash

set -e

show_help() {
    echo "$0 [-c path/to/cvat/utils/cli/cli.py] [-n localhost] user:pass labels.json path/to/share_folder"
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

if [ "$#" -lt 3 ]; then
    echo "Insufficient number of arguments"
    show_help
    exit 1
fi

auth=$1 # username:pass-env
labels=$2
share_folder=$3
