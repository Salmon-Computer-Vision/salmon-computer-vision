#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md

import argparse
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
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

LOCAL_DIR_PATH = "/media/local_hdd"
LOGS_DIR_PATH = "logs/salmonmd_logs"

def setup_file_logging(logs_dir: Path, loglevel: int, save_prefix=None) -> Path:
    """
    Attach a TimedRotatingFileHandler that rolls over at midnight with UTC timezone
    """

    name = "salmonmd_log"
    if save_prefix is not None:
        name = f"{save_prefix}_{name}"

    log_file = logs_dir / name  # base name; rotations get date suffix

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",     # rotate every midnight
        interval=1,
        encoding="utf-8",
        utc=True,
    )

    # Add date suffix to rotated files (e.g. salmonmd_log.20251209)
    file_handler.suffix = "%Y%m%d"

    file_handler.setLevel(loglevel)
    file_handler.setFormatter(formatter)
    rootlogger.addHandler(file_handler)

    return log_file

def install_excepthook():
    """
    Ensure any uncaught exceptions are logged via the root logger.
    """
    def handle_exception(exc_type, exc_value, exc_traceback):
        # Let KeyboardInterrupt behave normally
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.getLogger().error(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception

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
    save_cont_video = not args.no_cont if args.no_cont is not None else True
    is_video = args.video if args.video is not None else False

    save_prefix = None
    if args.test:
        site_save_path = Path(args.save_folder)
        logs_dir = Path(LOCAL_DIR_PATH)
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        if args.device_id is not None:
            device_id = args.device_id
            save_prefix = f"{orgid}-{site_name}-{args.device_id}"
        site_save_path = Path(args.save_folder) / orgid / site_name / device_id
        logs_dir = Path(LOCAL_DIR_PATH) / orgid / site_name / device_id / LOGS_DIR_PATH

    site_save_path.mkdir(exist_ok=True, parents=True)
    logs_dir.mkdir(exist_ok=True, parents=True)

    log_file = setup_file_logging(logs_dir, args.loglevel, save_prefix)

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
    det = md.MotionDetector(dataloader=vidloader, save_folder=site_save_path, save_prefix=save_prefix, ping_url=args.url, save_cont_video=save_cont_video, is_video=is_video)
    det.run(fps=int(args.fps), algo=args.algo, orin=args.orin, raspi=args.raspi)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("input", help="The input string. Normally an RTSP URL starting with rtsp:// of a camera. If it is a video path, set the --video flag.")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    parser.add_argument("--video", action='store_true', help="Set this flag for videos, and it will use the filename to determine clip filenames")
    parser.add_argument("--fps", default=None, help="Optionally set the FPS if it is not able to get it from input")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use the hostname to create the save paths")
    parser.add_argument("--orin", action='store_true', help="Set this flag to use Jetson Orin Nano settings")
    parser.add_argument("--raspi", action='store_true', help="Set this flag to use Raspi settings")
    parser.add_argument("--gstreamer", action='store_true', help="Set this flag to use Gstreamer capturing")
    parser.add_argument("--h265", action='store_true', help="Set this flag to use h265 decoding")
    parser.add_argument("--device-id", default=None, help="Set the device ID if should be different from the hostname")
    parser.add_argument("--algo", default="MOG2", choices=["MOG2", "CNT"], help="Set algorithm for motion detection")
    parser.add_argument("--url", default='https://google.com', help="Healthchecks URL to ping. This could be from healthchecks.io or another healthchecks service")
    parser.add_argument("--no-cont", action='store_true', help="Set this flag to not save continuous video")
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.INFO,
    )

    args = parser.parse_args()

    install_excepthook()

    try:
        main(args)
    except Exception:
        # Log fatal error with full traceback
        logger.exception("Fatal error in motion detector main()")
        raise

