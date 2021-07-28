#!/usr/bin/env bash
# This script is to be run by a systemd service to start the Jetson docker container and run the script to
# start the camera detection/recording script.
name=$1
dir_name=$2 # homesecurity
cd /home/salmonjetson/jetson-inference
sed -i -r "s/ -it (--name $name )?/ -i --name $name /" docker/run.sh
sed -i -r "s/ -i (--name $name )?/ -i --name $name /" docker/run.sh
docker/run.sh -v /home/salmonjetson/${dir_name}/:/${dir_name} -r /${dir_name}/cam.sh
