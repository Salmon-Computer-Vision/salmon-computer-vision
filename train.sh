#!/usr/bin/env bash
set -e

usage() { echo "Usage: $0 [-eh] [-u <cur_epoch>] [-n <num_steps>] [-p <epoch_steps>] [-k <checkpoint_steps>] [-c path/to/pipeline.config] [-m path/to/model/dir] [-d path/to/checkpoint/dir]" 1>&2; exit 1; }

# Use tensorboard to see eval and loss
# python -m tensorboard.main --logdir=models/my_ssd_resnet50_v1_fpn_640x640_longer/ --bind_all

pipeline=models/my_faster_rcnn_resnet50_v1_800x1333/pipeline.config
model_dir=models/my_faster_rcnn_resnet50_v1_800x1333
check_dir="${model_dir}"
num_steps=200000

# Training will stop after every epoch and 
epoch_steps=10000

checkpoint_steps=1000
cur_epoch=0

while getopts ":ehc:m:n:p:k:u:d:" o; do
    case "${o}" in
        c)
            pipeline=${OPTARG}
            ;;
        m)
            model_dir=${OPTARG}
            ;;
        e)
            eval=true
            ;;
        h)
            usage
            ;;
        n)
            num_steps=${OPTARG}
            ;;
        p)
            epoch_steps=${OPTARG}
            ;;
        k)
            checkpoint_steps=${OPTARG}
            ;;
        u)
            cur_epoch=${OPTARG}
            ;;
        d)
            check_dir=${OPTARG}
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

if [ "$eval" = true ]; then
    python ~/models/research/object_detection/model_main_tf2.py \
        --pipeline_config_path=${pipeline} \
        --model_dir=${model_dir} \
        --alsologtostderr \
        --eval_timeout=0 \
        --checkpoint_dir=${check_dir}
else
    for (( i=(cur_epoch + 1) * epoch_steps; i<=num_steps; i+=epoch_steps )); do
        python ~/models/research/object_detection/model_main_tf2.py \
            --pipeline_config_path=${pipeline} \
            --model_dir=${model_dir} \
            --checkpoint_every_n=${checkpoint_steps} \
            --num_train_steps=${i} \
            --alsologtostderr
        
        python ~/models/research/object_detection/model_main_tf2.py \
            --pipeline_config_path=${pipeline} \
            --model_dir=${model_dir} \
            --alsologtostderr \
            --eval_timeout=0 \
            --checkpoint_dir=${model_dir}
    done
fi
