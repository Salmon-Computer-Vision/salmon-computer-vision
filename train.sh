#!/usr/bin/env bash

usage() { echo "Usage: $0 [-e] [-h] [-c path/to/pipeline.config] [-m path/to/model/dir]" 1>&2; exit 1; }

pipeline=models/my_faster_rcnn_resnet50_v1_800x1333/pipeline.config
model_dir=models/my_faster_rcnn_resnet50_v1_800x1333

while getopts ":c:m:e:h" o; do
    case "${o}" in
        c)
            pipeline=${OPTARG}
            ;;
        m)
            model_dir=${OPTARG}
            ;;
        e)
            eval=true
        h)
            usage
            ;;
        \?)
            echo "Invalid option"
            usage
            ;;
        :)
            echo "Missing argument"
            usage
            ;;
    esac
done

if [ eval = true ]; then
    python ~/models/research/object_detection/model_main_tf2.py \
        --pipeline_config_path=${pipeline} \
        --model_dir=${model_dir} \
        --alsologtostderr \
        --checkpoint_dir=${model_dir}
else
    python ~/models/research/object_detection/model_main_tf2.py \
        --pipeline_config_path=${pipeline} \
        --model_dir=${model_dir} \
        --alsologtostderr \
fi
