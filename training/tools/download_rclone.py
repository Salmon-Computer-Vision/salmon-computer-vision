#!/usr/bin/env python3
import os
import subprocess
import argparse
from pathlib import Path

def main(args):
    SOURCE = "aws"
    OUTPUT_DIR = Path("frames")
    MOTION_VID_DIR = "motion_vids"


    for filename in os.listdir(args.input):
        download_cmd = ["rclone", "copy", "-v"]
        print(filename)
        parts = filename.split('-')
        org = parts[0]
        site = parts[1]

        datetime_parts = parts[3].split('_')
        device = f"{parts[2]}-{datetime_parts[0]}"

        print(org, site, device)

        output_vid_dir = OUTPUT_DIR / org / site / device / MOTION_VID_DIR

        download_cmd.append(f"{SOURCE}:{args.bucket}/{org}/{site}/{device}/{MOTION_VID_DIR}/{filename}")
        download_cmd.append(output_vid_dir)

        subprocess.run(download_cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Downloads and extracts the frames and puts it next to YOLO labels.")
    parser.add_argument("input", help="Input folder")
    parser.add_argument("bucket", help="AWS Bucket")
    args = parser.parse_args()

    main(args)
