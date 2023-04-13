#!/usr/bin/env bash

cam_ip=192.168.1.191
stream_name=YourStreamName
access_key=youraccesskey
secret_key=yoursecretkey
rtsp_url="rtsp://${cam_ip}/user=admin&password=&channel=0&stream=1.sdp?"

export LD_LIBRARY_PATH=/opt/awssdk/amazon-kinesis-video-streams-producer-sdk-cpp/kinesis-video-native-build/downloads/local/lib:$LD_LIBRARY_PATH
export PATH=/opt/awssdk/amazon-kinesis-video-streams-producer-sdk-cpp/kinesis-video-native-build/downloads/local/bin:$PATH
export GST_PLUGIN_PATH=/opt/awssdk/amazon-kinesis-video-streams-producer-sdk-cpp/kinesis-video-native-build/downloads/local/lib:$GST_PLUGIN_PATH

gst-launch-1.0 -v rtspsrc location="${rtsp_url}" \
    short-header=TRUE ! rtph264depay ! h264parse ! kvssink stream-name="${stream_name}" \
    access-key="${access_key}" secret-key="${secret_key}"
