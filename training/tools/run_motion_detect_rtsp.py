#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md

import argparse
import os
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)
logger = logging.getLogger(__name__)

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
    save_prefix = None
    if args.test:
        site_save_path = args.save_folder
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        if args.device_id is not None:
            device_id = args.device_id
            save_prefix = f"{orgid}-{site_name}-{args.device_id}"
        site_save_path = os.path.join(args.save_folder, orgid, site_name, device_id)

    if not os.path.exists(site_save_path):
        os.makedirs(site_save_path)

    if args.gstreamer:
        #input_str = f"rtspsrc location={args.rtsp_url} ! rtph265depay ! h265parse ! avdec_h265 ! v4l2convert ! video/x-raw,format=BGR ! appsink drop=1"
        input_str = f"rtspsrc location={args.rtsp_url} ! decodebin ! v4l2convert ! video/x-raw,format=BGR ! appsink drop=1"
    else:
        input_str = args.rtsp_url

    logger.info(input_str)
    vidloader = vl.VideoLoader([input_str], gstreamer_on=args.gstreamer)

    logger.info(f"save_prefix: {save_prefix}")
    det = md.MotionDetector(vidloader, site_save_path, save_prefix)
    det.run(fps=args.fps, orin=args.orin, raspi=args.raspi)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("rtsp_url", help="The RTSP URL of the camera")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    parser.add_argument("--fps", default=None, help="Optionally set the FPS if it is not able to get it from the camera")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use site save path")
    parser.add_argument("--orin", action='store_true', help="Set this flag to use Jetson Orin Nano settings")
    parser.add_argument("--raspi", action='store_true', help="Set this flag to use Raspi settings")
    parser.add_argument("--gstreamer", action='store_true', help="Set this flag to use Gstreamer capturing")
    parser.add_argument("--device-id", default=None, help="Set the device ID if should be different from the hostname")
    args = parser.parse_args()

    main(args)

