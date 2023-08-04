#!/usr/bin/env bash
name=$1
rtsp_url="$2"
stream_name=$3

docker run -i --rm --network host --name "$name" \
    -v /opt/vc:/opt/vc \
    -v /media/usb0:/media/usb0 \
    546150905175.dkr.ecr.us-west-2.amazonaws.com/kinesis-video-producer-sdk-cpp-raspberry-pi \
    "/opt/vc/rtsp_stream_file.sh" "$rtsp_url" $stream_name
