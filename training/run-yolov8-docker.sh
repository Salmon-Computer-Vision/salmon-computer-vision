#!/usr/bin/env bash

docker run --rm -it --ipc=host -p 8888:8888 --gpus all -v $PWD:/training -w /training yolov8-dev jupyter-lab --allow-root
