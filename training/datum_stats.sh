#!/usr/bin/env bash
dir="$1"

#parallel datum stats --image-stats False {} ::: "$dir"/*

i=0
for d in "$dir"/*; do
    (
    mkdir $i
    cd $i
    datum stats --image-stats False $d &
    )
    ((i=i+1))
done