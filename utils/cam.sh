#!/bin/env bash
ffmpeg -rtsp_transport tcp -i "rtsp://11.0.0.106/av0_0" -c:v h264_v4l2m2m -f segment -segment_time 3600 -strftime 1 "%m-%d-%Y %H-%M-%S Coquitlam Dam.mp4"
