#!/usr/bin/env bash
url="rtsp://10.0.0.89/av0_0"
#url="rtsp://10.0.0.98:554/user=admin&password=&channel=1&stream=0.sdp?"
#encode="h264_v4l2m2m"
encode=h264_omx
scale="1280:720"
dir=/media/usb0
suffix=$1

rec_dir="${dir}/record"

if [ ! -d "${rec_dir}" ]; then 
    mkdir -p "$rec_dir"
fi

ffmpeg -rtsp_transport tcp -r 25 -i "$url" -c:v "$encode" -vf scale="$scale" -r 15 -b:v 800k -an -f segment -segment_time 3600 -reset_timestamps 1 -strftime 1 "${rec_dir}/%m-%d-%Y_%H-%M-%S_${suffix}.mp4"
