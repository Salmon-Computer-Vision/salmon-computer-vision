#!/usr/bin/env bash
usage() { echo "Usage: $0 [-d docker-image:tag] path/to/dataset" 1>&2; exit 1; }

while getopts ":d:h" o; do
    case "${o}" in
        d)
            image=${OPTARG}
            ;;
        h)
            echo "Help"
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
shift $((OPTIND -1))

dataset=$1

[ "$#" -eq 1 ] || (echo "1 argument required for the dataset path, $# provided"; usage)

docker run -it -v "$PWD:/home/tensorflow/code" \
    -v "${dataset}:/home/tensorflow/data" \
    -w /home/tensorflow/code \
    ${image}
