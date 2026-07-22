#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md

import argparse
import os
import re
import sys
import logging
import threading
from logging.handlers import TimedRotatingFileHandler
import datetime
from pathlib import Path
import time
from typing import List, Optional, Tuple
import multiprocessing as mp

# Set up logging
log_format = '%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s'
rootlogger = logging.getLogger()
rootlogger.setLevel(logging.INFO)
formatter = logging.Formatter(log_format)
formatter.converter = time.gmtime
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
rootlogger.addHandler(console_handler)

logger = logging.getLogger(__name__)

LOCAL_DIR_PATH = "/media/local_hdd"
LOGS_DIR_PATH = "device_logs/raw"

class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Rename rotated files from:
        <name>.YYYYMMDD
    to:
        <name>_YYYYMMDD.txt
    """

    def rotation_filename(self, default_name: str) -> str:
        path = Path(default_name)

        # Example:
        #   default_name = "/path/to/motion_detection_logs.20251209"
        #   path.stem     = "motion_detection_logs"
        #   path.suffix   = ".20251209"
        date_part = path.suffix.lstrip(".")
        base_name = path.stem

        new_name = f"{base_name}_{date_part}.txt"
        return str(path.with_name(new_name))

def setup_file_logging(logs_dir: Path, loglevel: int, save_prefix=None) -> Path:
    """
    Attach a TimedRotatingFileHandler that rolls over at midnight with UTC timezone
    """

    name = "motion_detection_logs"
    if save_prefix is not None:
        name = f"{save_prefix}_{name}"

    log_file = logs_dir / name  # base name; rotations get date suffix

    file_handler = CustomTimedRotatingFileHandler(
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


CAM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _build_input_str(url: str, gstreamer: bool, h265: bool) -> str:
    """Wrap a raw RTSP URL in the appropriate pipeline when gstreamer is on.

    Extracted so both the single-cam and multi-cam paths build their
    per-URL pipeline the same way.
    """
    if gstreamer:
        if h265:
            return (
                f"rtspsrc location={url} ! decodebin ! queue ! v4l2convert "
                "! video/x-raw,format=BGR ! appsink drop=1"
            )
        return (
            f"rtspsrc location={url} ! rtph264depay ! h264parse "
            "! v4l2h264dec ! videoconvert ! appsink"
        )
    return url


def _parse_multi_camera_args(args) -> Tuple[List[str], List[str]]:
    """Parse and validate the multi-camera CLI inputs.

    Returns (urls, cam_names). Raises SystemExit (via argparse-style ValueError)
    on invalid input.
    """
    urls = [u.strip() for u in args.input.split(',') if u.strip()]
    if len(urls) < 2:
        raise ValueError(
            "--multi-camera requires at least 2 comma-separated RTSP URLs "
            f"in the input argument; got {len(urls)}: {args.input!r}"
        )

    if args.cam_names:
        cam_names = [c.strip() for c in args.cam_names.split(',')]
        if any(not c for c in cam_names):
            raise ValueError(
                f"--cam-names contains empty entries: {args.cam_names!r}"
            )
    else:
        cam_names = [f"cam{i+1}" for i in range(len(urls))]

    if len(cam_names) != len(urls):
        raise ValueError(
            f"Number of --cam-names ({len(cam_names)}) does not match "
            f"number of RTSP URLs ({len(urls)})"
        )

    for name in cam_names:
        if not CAM_NAME_RE.match(name):
            raise ValueError(
                f"cam name {name!r} is invalid: must match [A-Za-z0-9_-]+"
            )

    if len(set(cam_names)) != len(cam_names):
        raise ValueError(f"cam names must be unique; got {cam_names}")

    return urls, cam_names


def _run_detector_in_thread(det, fps, algo, orin, raspi, staging, cam_name, cpu_h264, bitrate,
        bgsub_threshold,
        cnt_min_pixel_stability,
        cnt_max_pixel_stability,
        fg_threshold,
        morph_kernel_size,
        erode_iter,
        dilate_iter,
        min_contour_area,
        min_contour_area_ratio,
        motion_trigger_seconds,
        warmup_seconds,
    ):
    """Thread target that logs any crash in the cam's detector without
    bringing down the other cams' threads."""
    try:
        det.run(fps=fps, algo=algo, orin=orin, raspi=raspi, staging=staging, cpu_h264=cpu_h264, bitrate=bitrate,
                bgsub_threshold=bgsub_threshold,
                cnt_min_pixel_stability=cnt_min_pixel_stability,
                cnt_max_pixel_stability=cnt_max_pixel_stability,
                fg_threshold=fg_threshold,
                morph_kernel_size=morph_kernel_size,
                erode_iter=erode_iter,
                dilate_iter=dilate_iter,
                min_contour_area=min_contour_area,
                min_contour_area_ratio=min_contour_area_ratio,
                motion_trigger_seconds=motion_trigger_seconds,
                warmup_seconds=warmup_seconds,
                )
    except Exception:
        logger.exception("[%s] detector thread crashed", cam_name)


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

    fps = int(args.fps)

    if args.multi_camera:
        urls, cam_names = _parse_multi_camera_args(args)
        logger.info(
            "Multi-camera mode: %d cameras, names=%s", len(urls), cam_names
        )

        # Share ONE coordinator across all cam threads. Timing defaults come
        # from the module-level constants in motion_detect_stream.py; changing
        # those constants automatically applies to both single- and multi-cam.
        coordinator = md.MotionEventCoordinator(cam_names)

        detectors = []
        for url, cam_name in zip(urls, cam_names):
            input_str = _build_input_str(url, args.gstreamer, args.h265)
            logger.info("[%s] input: %s", cam_name, input_str)
            vidloader = vl.VideoLoader(
                [input_str],
                gstreamer_on=args.gstreamer,
                buffer_size=5 * fps,
                target_fps=fps,
                camera_width=args.camera_width,
                camera_height=args.camera_height,
                camera_fps=args.camera_fps,
                camera_fourcc=args.camera_fourcc,
                camera_backend=args.camera_backend,
            )
            cam_save_prefix = (
                f"{save_prefix}_{cam_name}" if save_prefix is not None else cam_name
            )
            det = md.MotionDetector(
                dataloader=vidloader,
                save_folder=site_save_path,
                save_prefix=cam_save_prefix,
                ping_url=args.url,
                save_cont_video=save_cont_video,
                is_video=is_video,
                coordinator=coordinator,
                cam_name=cam_name,
            )
            detectors.append((det, cam_name))

        threads = []
        for det, cam_name in detectors:
            t = threading.Thread(
                target=_run_detector_in_thread,
                args=(
                    det, fps, args.algo, args.orin, args.raspi, 
                    args.staging, cam_name, args.cpu_h264, args.bitrate,
                    args.bgsub_threshold,
                    args.cnt_min_pixel_stability,
                    args.cnt_max_pixel_stability,
                    args.fg_threshold,
                    args.morph_kernel_size,
                    args.erode_iter,
                    args.dilate_iter,
                    args.min_contour_area,
                    args.min_contour_area_ratio,
                    args.motion_trigger_seconds,
                    args.warmup_seconds,
                ),
                name=f"MotionDetector-{cam_name}",
                daemon=False,
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
        logger.info("All multi-camera detector threads have exited.")
        return

    # --- Single-camera path (today's behavior) ---
    input_str = _build_input_str(args.input, args.gstreamer, args.h265)
    logger.info(input_str)
    vidloader = vl.VideoLoader(
            [input_str], 
            gstreamer_on=args.gstreamer, 
            buffer_size=5*fps, 
            target_fps=fps,
            camera_width=args.camera_width,
            camera_height=args.camera_height,
            camera_fps=args.camera_fps,
            camera_fourcc=args.camera_fourcc,
            camera_backend=args.camera_backend,
    )

    logger.info(f"save_prefix: {save_prefix}")
    det = md.MotionDetector(dataloader=vidloader, save_folder=site_save_path, save_prefix=save_prefix, ping_url=args.url, save_cont_video=save_cont_video, is_video=is_video)
    det.run(
        fps=fps,
        algo=args.algo,
        orin=args.orin,
        raspi=args.raspi,
        cpu_h264=args.cpu_h264,
        staging=args.staging,
        bitrate=args.bitrate,
        bgsub_threshold=args.bgsub_threshold,
        cnt_min_pixel_stability=args.cnt_min_pixel_stability,
        cnt_max_pixel_stability=args.cnt_max_pixel_stability,
        fg_threshold=args.fg_threshold,
        morph_kernel_size=args.morph_kernel_size,
        erode_iter=args.erode_iter,
        dilate_iter=args.dilate_iter,
        min_contour_area=args.min_contour_area,
        min_contour_area_ratio=args.min_contour_area_ratio,
        motion_trigger_seconds=args.motion_trigger_seconds,
        warmup_seconds=args.warmup_seconds,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("input", help="The input string. Normally an RTSP URL starting with rtsp:// of a camera. If it is a video path, set the --video flag.")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    parser.add_argument("--video", action='store_true', help="Set this flag for videos, and it will use the filename to determine clip filenames")
    parser.add_argument("--fps", default=None, help="Optionally set the FPS if it is not able to get it from input")
    parser.add_argument("--camera-width", type=int, default=None, help="Works only for USB camera. Request camera width")
    parser.add_argument("--camera-height", type=int, default=None, help="Works only for USB camera. Request camera height")
    parser.add_argument("--camera-fps", type=int, default=None, help="Works only for USB camera. Request camera FPS. The FPS will still be clamped to target FPS")
    parser.add_argument("--camera-fourcc", default=None, choices=["MJPG", "YUYV"], help="Works only for USB camera. Request camera fourcc format")
    parser.add_argument("--camera-backend", default="v4l2", choices=["default", "v4l2"], help="Works only for USB camera. Request camera backend")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use the hostname to create the save paths")
    parser.add_argument("--orin", action='store_true', help="Set this flag to use Jetson Orin Nano settings")
    parser.add_argument("--raspi", action='store_true', help="Set this flag to use Raspi settings")
    parser.add_argument("--cpu_h264", action='store_true', help="Set this flag to use CPU H264 ultra fast settings")
    parser.add_argument("--bitrate", default=1200, help="Set the bitrate")
    parser.add_argument("--gstreamer", action='store_true', help="Set this flag to use Gstreamer capturing")
    parser.add_argument("--h265", action='store_true', help="Set this flag to use h265 decoding")
    parser.add_argument("--device-id", default=None, help="Set the device ID if should be different from the hostname")
    parser.add_argument("--algo", default="MOG2", choices=["MOG2", "CNT"], help="Set algorithm for motion detection")
    parser.add_argument("--bgsub-threshold", type=float, default=30, help="Lower threshold means more pixels easily become the foreground")
    parser.add_argument("--cnt-min-pixel-stability", type=int, default=1)
    parser.add_argument("--cnt-max-pixel-stability", type=int, default=7)
    parser.add_argument("--fg-threshold", type=int, default=244)
    parser.add_argument("--morph-kernel-size", type=int, default=7, help="Smaller kernel is more sensitive to small/thin motion")
    parser.add_argument("--erode-iter", type=int, default=1, help="More iterations takes more time but can smooth out motion better")
    parser.add_argument("--dilate-iter", type=int, default=1, help="More iterations takes more time but can increase smaller motion blobs")
    parser.add_argument("--min-contour-area", type=int, default=5000, help="Area threshold of how big the motion must be before triggering")
    parser.add_argument("--min-contour-area-ratio", type=float, default=None, help="Replaces area and determines based on ratio of the entire frame. Must be fractional")
    parser.add_argument("--motion-trigger-seconds", type=float, default=0.4, help="How many seconds before motion is triggered. Can be fractional; eg. 10 FPS, 0.2 -> 2 frames.")
    parser.add_argument("--warmup-seconds", type=float, default=1.0, help="Number of seconds to warmup at the start of the program before detecting motion. Required as the background needs to be established first.")
    parser.add_argument("--url", default='https://google.com', help="Healthchecks URL to ping. This could be from healthchecks.io or another healthchecks service")
    parser.add_argument("--no-cont", action='store_true', help="Set this flag to not save continuous video")
    parser.add_argument("--staging", action='store_true', help="Set this flag to save to a staging folder for edge salmon counting processing")
    parser.add_argument(
        "--multi-camera", action='store_true', dest='multi_camera',
        help=(
            "Enable multi-camera mode. The positional input is then treated "
            "as a comma-separated list of RTSP URLs (N >= 2). All cameras "
            "share lock-step clip boundaries (same event_id, same "
            "part_number count, same wall-clock length) via a coordinator."
        ),
    )
    parser.add_argument(
        "--cam-names", default=None, dest='cam_names',
        help=(
            "Comma-separated camera names used to disambiguate clips in "
            "multi-camera mode. Each name must match [A-Za-z0-9_-]+, no "
            "duplicates. Length must equal the number of RTSP URLs in the "
            "positional input. Defaults to cam1,cam2,...,camN."
        ),
    )
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.INFO,
    )

    args = parser.parse_args()

    if args.multi_camera:
        try:
            _parse_multi_camera_args(args)
        except ValueError as exc:
            parser.error(str(exc))

    install_excepthook()

    try:
        mp.set_start_method("spawn", force=True)
        main(args)
    except Exception:
        # Log fatal error with full traceback
        logger.exception("Fatal error in motion detector main()")
        raise

