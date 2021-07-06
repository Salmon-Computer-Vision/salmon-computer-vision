#!/bin/env bash
url="rtsp://11.0.0.106/av0_0"
#url="rtsp://10.0.0.98:554/user=admin&password=&channel=1&stream=0.sdp?"
#encode="h264_v4l2m2m"
encode=h264_omx
scale="1280:-1"

ffmpeg -rtsp_transport tcp -i "$url" -c:v "$encode" -vf scale="$scale" -f segment -segment_time 3600 -strftime 1 "%m-%d-%Y %H-%M-%S Coquitlam Dam.mp4"
