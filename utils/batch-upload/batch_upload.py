#!/usr/bin/env python3

import subprocess
from dotenv import dotenv_values

def main():
    config = dotenv_values(".env")
    SITE_NAME = config.get('SITE_NAME')
    ORGID = config.get('ORGID')
    BUCKET = config.get('BUCKET')
    
    COMMON_FLAGS = '--bwlimit=0 --buffer-size=128M --transfers=1 --log-level INFO'.split()
    MOTION_VIDS_INCLUDE = ['--include', f"/{SITE_NAME}/*/motion_vids/**"]
    MOTION_VIDS_METADATA_INCLUDE = ['--include', f"/{SITE_NAME}/*/motion_vids_metadata/**"]
    LOCATION = [f"./{ORGID}", f'aws:{BUCKET}/{ORGID}']
    CONFIG = ["--config", "rclone.conf"]

    # TODO: Change depending on distribution
    UPLOAD_LOC = ['rclone']

    UPLOAD_CMD = ['copy']

    CMD = UPLOAD_LOC + UPLOAD_CMD + COMMON_FLAGS + MOTION_VIDS_INCLUDE + \
            MOTION_VIDS_METADATA_INCLUDE + CONFIG + LOCATION
    print(CMD)

if __name__ == "__main__":
    main()
