#!/usr/bin/env bash

docker run --rm -it --ipc=host -p 8888:8888 --gpus all -v $PWD:/training -w /training \
    -v /mnt/shiorissd4tb/masamim:/mnt/shiorissd4tb/masamim \
    -v /home/masamim/salmon-computer-vision/utils/:/home/masamim/salmon-computer-vision/utils/ \
    yolov8-dev jupyter-lab --allow-root
