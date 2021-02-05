salmon_vids=$1
dataset=$2

docker run --gpus all -it -v $PWD:/tmp \
    -v "${salmon_vids}:/tmp/data" \
    -v "${dataset}:/tmp/labels" \
    -w /tmp \
    od
