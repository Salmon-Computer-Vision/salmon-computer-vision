#!/usr/bin/env python3

import subprocess
from dotenv import dotenv_values
from pathlib import Path

def main():
    config = dotenv_values(".env")

    SITE_NAME = config.get('SITE_NAME')
    ORGID = config.get('ORGID')
    BUCKET = config.get('BUCKET')
    
    COMMON_FLAGS = '--bwlimit=0 --buffer-size=128M --transfers=1 --log-level INFO'.split()
    MOTION_VIDS_INCLUDE = ['--include', f"/{SITE_NAME}/*/motion_vids/**"]
    MOTION_VIDS_METADATA_INCLUDE = ['--include', f"/{SITE_NAME}/*/motion_vids_metadata/**"]
    DETECTIONS_INCLUDE = f"--include /{SITE_NAME}/*/detections/**".split()
    COUNTS_INCLUDE = f"--include /{SITE_NAME}/*/counts/** --include /{SITE_NAME}/*/*.csv".split()
    LOCATION = [str(Path("..") / ".." / ORGID), f'aws:{BUCKET}/{ORGID}']
    CONFIG = ["--config", "rclone.conf"]

    UPLOAD_LOC = [str(Path('rclone-install') / 'rclone')]

    UPLOAD_CMD = ['copy']

    MOTION_VIDS_CMD = UPLOAD_LOC + UPLOAD_CMD + COMMON_FLAGS + \
            MOTION_VIDS_INCLUDE + MOTION_VIDS_METADATA_INCLUDE + \
            DETECTIONS_INCLUDE + COUNTS_INCLUDE + \
            CONFIG + LOCATION
    print(MOTION_VIDS_CMD)

    subprocess.run(MOTION_VIDS_CMD)

if __name__ == "__main__":
    main()
