docker run --gpus all -it -v $PWD:/tmp \
    -v '/home/sami/gdrive/Salmon Videos:/tmp/data' \
    -v '/home/sami/salmon-count-labels:/tmp/labels' \
    -w /tmp \
    od
