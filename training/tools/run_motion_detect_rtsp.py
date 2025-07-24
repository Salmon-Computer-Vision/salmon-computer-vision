#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md

import argparse
import os
import sys
import logging
import datetime
from pathlib import Path

# Set up logging
log_format = '%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s'
rootlogger = logging.getLogger()
rootlogger.setLevel(logging.INFO)
formatter = logging.Formatter(log_format)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
rootlogger.addHandler(console_handler)

logger = logging.getLogger(__name__)

LOGS_DIR_PATH = "logs/salmonmd_logs"

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
        site_save_path = Path(args.save_folder)
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        if args.device_id is not None:
            device_id = args.device_id
            save_prefix = f"{orgid}-{site_name}-{args.device_id}"
        site_save_path = Path(args.save_folder) / orgid / site_name / device_id

    site_save_path.mkdir(exist_ok=True, parents=True)

    logs_dir = site_save_path / LOGS_DIR_PATH
    logs_dir.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d")
    log_file = logs_dir / f"salmonmd_logs_{timestamp}.txt"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    rootlogger.addHandler(file_handler)

    logger.info(f"Writing logs to {log_file}")

    if args.gstreamer:
        #input_str = f"rtspsrc location={args.input} ! rtph265depay ! h265parse ! avdec_h265 ! v4l2convert ! video/x-raw,format=BGR ! appsink drop=1"
        if args.h265:
            input_str = f"rtspsrc location={args.input} ! decodebin ! queue ! v4l2convert ! video/x-raw,format=BGR ! appsink drop=1"
        else:
            #input_str = f"rtspsrc location={args.input} ! rtph264depay ! queue ! h264parse ! v4l2h264dec ! queue ! v4l2convert ! video/x-raw,format=BGR ! appsink drop=1"
            input_str = f"rtspsrc location={args.input} ! rtph264depay ! h264parse ! v4l2h264dec ! videoconvert ! appsink"
    else:
        input_str = args.input

    logger.info(input_str)
    vidloader = vl.VideoLoader([input_str], gstreamer_on=args.gstreamer, buffer_size=2*int(args.fps), target_fps=int(args.fps))

    logger.info(f"save_prefix: {save_prefix}")
    det = md.MotionDetector(dataloader=vidloader, save_folder=site_save_path, save_prefix=save_prefix, ping_url=args.url)
    det.run(fps=int(args.fps), algo=args.algo, orin=args.orin, raspi=args.raspi)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("input", help="The input string. Normally an RTSP URL starting with rtsp:// of a camera. If it is a video path, set the --video flag.")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    parser.add_argument("--fps", default=None, help="Optionally set the FPS if it is not able to get it from input")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use the hostname to create the save paths")
    parser.add_argument("--orin", action='store_true', help="Set this flag to use Jetson Orin Nano settings")
    parser.add_argument("--raspi", action='store_true', help="Set this flag to use Raspi settings")
    parser.add_argument("--gstreamer", action='store_true', help="Set this flag to use Gstreamer capturing")
    parser.add_argument("--h265", action='store_true', help="Set this flag to use h265 decoding")
    parser.add_argument("--device-id", default=None, help="Set the device ID if should be different from the hostname")
    parser.add_argument("--algo", default="MOG2", choices=["MOG2", "CNT"], help="Set algorithm for motion detection")
    parser.add_argument("--url", default='https://google.com', help="Healthchecks URL to ping. This could be from healthchecks.io or another healthchecks service")
    args = parser.parse_args()

    main(args)

