#!/usr/bin/env bash
name=$1
cam_ip=$2
stream_name=$3

docker run -i --rm --network host --name "$name" \
    -v /opt/vc:/opt/vc \
    546150905175.dkr.ecr.us-west-2.amazonaws.com/kinesis-video-producer-sdk-cpp-raspberry-pi \
    "/opt/vc/${script}" $cam_ip $stream_name
