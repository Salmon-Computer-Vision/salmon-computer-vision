#!/usr/bin/env bash
source=$1
dest=$2

datum export -p "$source" -o "$dest" -f tf_detection_api -- --save-images
