#!/usr/bin/env bash
die () {
    echo >&2 "$@"
    exit 1
}

dataset=$1

[ "$#" -eq 1 ] || die "1 argument required for the dataset path, $# provided"

docker run --gpus all -it -v $PWD:code \
    -v "${dataset}:data" \
    -w code \
    od
