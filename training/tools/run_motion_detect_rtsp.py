#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md

import argparse
import os

def read_rtsp_url(file_path):
    """Read RTSP URL from the specified file."""
    with open(file_path, 'r') as file:
        return file.readline().strip()

def get_orgid_and_site_name(name):
    parts = name.split('-')
    orgid = parts[0]
    site_name = parts[1]
    device_id = '-'.join(parts[2:])
    return orgid, site_name, device_id


def main(args):
    if args.test:
        site_save_path = args.save_folder
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        site_save_path = os.path.join(args.save_folder, orgid, site_name, device_id)

    if not os.path.exists(site_save_path):
        os.makedirs(site_save_path)

    vidloader = vl.VideoLoader([args.rtsp_url])

    det = md.MotionDetector(vidloader, site_save_path)
    det.run(fps=args.fps)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("rtsp_url", help="The RTSP URL of the camera")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    parser.add_argument("--fps", default=None, help="Optionally set the FPS if it is not able to get it from the camera")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use site save path")
    args = parser.parse_args()

    main(args)

