#!/usr/bin/env bash
set -e

min_num_param=2
if [ "$#" -lt $min_num_param ]; then
    echo "Must have at least ${min_num_param} parameters"
    exit 1
fi

source=$1
dest=$2

mkdir -p "$dest"
#merged_dir="${dest}/merged"
#datum create -o "$merged_dir"
find "${source}" -name '*M*.m4v' ! -name '._*' | while read vid; do
    vid_base="${vid##*/}"
    vid_name="${vid_base%.*}"
    name="${vid_name// /_}" # Substitute spaces with underscores
    frames_dest="${dest}/${name}"

    echo "Splitting $vid_name"
    # TODO: Paralellize with `sem`
    datum util split_video -i "$vid" -o "$frames_dest" -n "${name}_%06d"
    #if [ -d "${merged_dir}/annotations" ]; then
    #    datum patch --overwrite "$merged_dir" "$frames_dest":image_dir
    #else
    #    datum convert -i "$frames_dest" -if image_dir -f datumaro -o "$merged_dir"
    #fi
done
