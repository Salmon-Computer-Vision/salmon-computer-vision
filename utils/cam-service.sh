#!/usr/bin/env bash
# This script is to be run by a systemd service to start the Jetson docker container and run the script to
# start the camera detection/recording script.
cd /home/salmonjetson/jetson-inference
docker/run.sh -v /home/salmonjetson/homesecurity/:/homesecurity -r /homesecurity/cam.sh
