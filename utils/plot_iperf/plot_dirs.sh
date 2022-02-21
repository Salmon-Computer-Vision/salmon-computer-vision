#!/usr/bin/env bash
set -e

# Must be in same folder as plot_iperfcsv.py

src_dir="$1"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path/to/src_dir>"
    echo "Plots and saves iperf csv files to \"figures\""
    exit 0
fi

download()
{
    dir=$1
    basedir=$2
    region_name=$3
    dest=$4
    python3 plot_iperfcsv.py "${dir}"/*down.* -n "Starlink Download (${region_name})" -f ${dest}/${basedir}_down
}

upload()
{
    dir=$1
    basedir=$2
    region_name=$3
    dest=$4
    sem -j+0 python3 plot_iperfcsv.py "${dir}"/*up.* -n "Starlink Upload (${region_name})" -f ${dest}/${basedir}_up
}

export -f download
export -f upload

dest='figures'
mkdir -p "$dest"
for dir in "$src_dir"/*/; do
    basedir=$(basename "$dir")
    region_name=${basedir##*_}

    # Plot downloads
    sem -j+0 download "$dir" "$basedir" "$region_name" "$dest"

    # Plot uploads
    sem -j+0 upload "$dir" "$basedir" "$region_name" "$dest"
done
