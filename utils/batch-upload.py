#!/usr/bin/env python3

import subprocess

def main():
    COMMON_FLAGS = '--bwlimit=0 --buffer-size=128M --transfers=1 --log-level INFO'.split()
    MOTION_VIDS_INCLUDE = ['--include', "/${SITE_NAME}/*/motion_vids/**"]
    MOTION_VIDS_METADATA_INCLUDE = ['--include', "/${SITE_NAME}/*/motion_vids_metadata/**"]
    LOCATION = ["${DRIVE}/${ORGID}", 'aws:${BUCKET}/${ORGID}']
    CONFIG = ["--config", "config/rclone/rclone.conf"]

    UPLOAD = 'rclone copy'.split()

    CMD = UPLOAD + COMMON_FLAGS + MOTION_VIDS_INCLUDE + \
            MOTION_VIDS_METADATA_INCLUDE + CONFIG + LOCATION
    print(CMD)

if __name__ == "__main__":
    main()
