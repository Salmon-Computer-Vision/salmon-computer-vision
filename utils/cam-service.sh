#!/usr/bin/env bash
# This script is to be run by a systemd service to start the Jetson docker container and run the script to
# start the camera detection/recording script.
cd /mnt/ssd/jetson-inference
/mnt/ssd/jetson-inference/docker/run.sh -v /mnt/ssd/homesecurity/:/homesecurity -r /homesecurity/cam.sh
