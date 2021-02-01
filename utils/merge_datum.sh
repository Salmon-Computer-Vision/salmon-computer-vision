#!/usr/bin/env bash
datum filter -e '/item/annotation' -m i+a -p 163 -o 163_filtered
datum transform -p 163_filtered/ -o 163_filtered -t rename --overwrite -- -e '|frame_(\d+)|163_\1|'
datum merge 162_filtered 163_filtered -o merged

