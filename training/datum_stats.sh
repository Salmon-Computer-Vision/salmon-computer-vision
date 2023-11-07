#!/usr/bin/env bash
dir="$1"

parallel datum stats --image-stats False {} ::: "$dir"/*