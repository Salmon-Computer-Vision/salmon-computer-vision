#!/usr/bin/env bash
# Add the following to `sudo crontab -e`
# 0 0 * * * systemctl restart cam-record.service

#url="rtsp://192.168.10.89/av0_0"
#url="rtsp://192.168.10.98:554/user=admin&password=&channel=1&stream=0.sdp?"
#encode="h264_v4l2m2m"
url=$1
suffix=$2
subdir=$3
encode=h264_omx
scale="1280:720"
drive=/media/usb0
dir="CoquitlamDamRecord"

today=`date +'%m-%d-%Y'`
rec_dir="${drive}/${dir}/${today}/${subdir}"

if [ ! -d "${rec_dir}" ]; then 
    mkdir -p "$rec_dir"
fi

ffmpeg -rtsp_transport tcp -i "$url" -c:v "$encode" -vf scale="$scale",fps=15 -b:v 800k -an -f segment -segment_time 3600 -reset_timestamps 1 -strftime 1 "${rec_dir}/%m-%d-%Y_%H-%M-%S_${suffix}.mp4"
