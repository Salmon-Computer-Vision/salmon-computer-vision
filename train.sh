#!/usr/bin/env bash

PIPELINE_CONFIG_PATH=models/my_ssd_mobilenet_v1_fpn/pipeline.config
MODEL_DIR=models/my_ssd_mobilenet_v1_fpn
python ~/models/research/object_detection/model_main_tf2.py \
    --pipeline_config_path=${PIPELINE_CONFIG_PATH} \
    --model_dir=${MODEL_DIR} \
    --alsologtostderr
