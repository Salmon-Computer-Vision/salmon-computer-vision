#!/usr/bin/env bash
die () {
    echo >&2 "$@"
    exit 1
}

dataset=$1

[ "$#" -eq 1 ] || die "1 argument required for the dataset path, $# provided"

docker run --gpus all -it -v "$PWD:/home/tensorflow/code" \
    -v "${dataset}:/home/tensorflow/data" \
    -w /home/tensorflow/code \
    od
