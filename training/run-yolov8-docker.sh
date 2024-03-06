#!/usr/bin/env bash

docker run --rm -it --ipc=host -p 8888:8888 --gpus all -v $PWD:/training -w /training \
    -v /mnt/shiorissd4tb:/mnt/shiorissd4tb \
    -v /mnt/ayumissd4tb:/mnt/ayumissd4tb \
    -v /home/masamim/salmon-computer-vision/utils/:/home/masamim/salmon-computer-vision/utils/ \
    yolov8-dev jupyter-lab --allow-root
