#!/usr/bin/env python3
import os
import subprocess
import argparse
from pathlib import Path

def main(args):
    SOURCE = "aws"
    OUTPUT_DIR = Path("frames")
    MOTION_VID_DIR = "motion_vids"

    download_cmd = ["rclone", "copy", "-v"]

    for filename in os.listdir(args.input):
        print(filename)
        parts = filename.split('-')
        org = parts[0]
        site = parts[1]

        datetime_parts = parts[3].split('_')
        device = f"{parts[2]}-{datetime_parts[0]}"

        print(org, site, device)

        download_cmd.append(f"{SOURCE}:{args.bucket}/{org}/{site}/{device}/{MOTION_VID_DIR}/{filename}")
        download_cmd.append(OUTPUT_DIR)

        subprocess.run(download_cmd)
        
        break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Downloads and extracts the frames and puts it next to YOLO labels.")
    parser.add_argument("input", help="Input folder")
    parser.add_argument("bucket", help="AWS Bucket")
    args = parser.parse_args()

    main(args)
