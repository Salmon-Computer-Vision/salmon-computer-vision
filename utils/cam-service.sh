#!/usr/bin/env bash
cd /mnt/ssd/jetson-inference
/mnt/ssd/jetson-inference/docker/run.sh -v /mnt/ssd/homesecurity/:/homesecurity -r /homesecurity/cam.sh
