#!/usr/bin/env bash

usage() { echo "Usage: $0 [-c path/to/pipeline.config] [-m path/to/model/dir]" 1>&2; exit 1; }

pipeline=models/my_faster_rcnn_resnet50_v1_640x640/pipeline.config
model_dir=models/my_faster_rcnn_resnet50_v1_640x640

while getopts ":c:m:h" o; do
    case "${o}" in
        c)
            pipeline=${OPTARG}
            ;;
        m)
            model_dir=${OPTARG}
            ;;
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

python ~/models/research/object_detection/model_main_tf2.py \
    --pipeline_config_path=${pipeline} \
    --model_dir=${model_dir} \
    --alsologtostderr
