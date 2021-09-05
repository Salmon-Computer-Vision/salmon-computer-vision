#!/usr/bin/env bash
# This script is to be run by a systemd service to start the Jetson docker container and run the script to
# start the camera detection/recording script.
name=$1
dir_name=$2 # homesecurity
tmp_sh=$(mktemp)

cd /home/salmonjetson/jetson-inference
sed -r "s/ -it (--name $name )?/ -i --name $name /" docker/run.sh > $tmp_sh
sed -i -r "s/ -i (--name .* )?(--rm)/ -i --name $name \2/" $tmp_sh
bash $tmp_sh -c cam-detect -v /home/salmonjetson/${dir_name}/:/${dir_name} -r /${dir_name}/cam.sh
