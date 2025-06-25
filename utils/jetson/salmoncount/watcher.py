#!/usr/bin/env python3
import os
import argparse
import time
import datetime
from pathlib import Path
import subprocess
import pickle
import yaml
import logging
import traceback
from ultralytics import YOLO

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pysalmcount.videoloader import VideoLoader
from pysalmcount.salmon_counter import SalmonCounter

# Set up logging
class BufferedHandler(logging.Handler):
    def __init__(self, buffer_size=10):
        super().__init__()
        self.buffer = []
        self.buffer_size = buffer_size

    def emit(self, record):
        self.buffer.append(self.format(record))
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        if self.buffer:
            for log_entry in self.buffer:
                print(log_entry)  # Replace with the desired output method, e.g., write to a file
            self.buffer = []

    def close(self):
        self.flush()
        super().close()

rootlogger = logging.getLogger()
rootlogger.setLevel(logging.INFO)

buffered_handler = BufferedHandler(buffer_size=50)
buffered_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s')
buffered_handler.setFormatter(formatter)
rootlogger.addHandler(buffered_handler)

logger = logging.getLogger(__name__)

DRIVE_DIR = Path("/app/drive/hdd")
MOTION_DIR_NAME = "motion_vids"
DETECTION_DIR_NAME = "detections"
COUNTS_DIR_NAME = "counts"
LOGS_DIR_PATH = "logs/salmoncount_logs"
CONFIG_PATH = Path("/app/config/2023_combined_salmon.yaml")
PROCESSED_FILE = Path("/app/config/processed_videos.pkl")

def get_orgid_and_site_name(name):
    parts = name.split('-')
    orgid = parts[0]
    site_name = parts[1]
    device_id = '-'.join(parts[2:])
    return orgid, site_name, device_id

def load_processed_videos():
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'rb') as f:
            return pickle.load(f)
    return set()

def save_processed_videos(processed_videos):
    with open(PROCESSED_FILE, 'wb') as f:
        pickle.dump(processed_videos, f)


class VideoHandler(FileSystemEventHandler):
    def __init__(self, detection_dir, counts_dir, weights_path):
        self.model = YOLO(weights_path)
        self.detection_dir = detection_dir
        self.counts_dir = counts_dir

        with open(CONFIG_PATH, 'r') as file:
            self.data = yaml.safe_load(file)

    def on_created(self, event):
        logger.info("New file event")
        if event.src_path.endswith(".mp4"):
            video_path = Path(event.src_path)
            if self.is_fully_written(video_path):
                self.process_video(video_path)
            else:
                logger.info(f"File {video_path} is still being written.")

    def is_fully_written(self, file_path, wait_time=5, check_interval=1):
        """Check if the file is fully written by monitoring its size."""
        initial_size = -1
        while True:
            current_size = file_path.stat().st_size
            if current_size == initial_size:
                return True
            initial_size = current_size
            time.sleep(check_interval)
    
    def process_video(self, video_path, drop_bounding_boxes=False, bound_line_ratio=0.5):
        counts_file = self.counts_dir / f"{video_path.stem}.csv"
        detections_dir = self.detection_dir / video_path.stem
        if not counts_file.exists():
            logger.info(f"Processing {video_path}")
            try:
                self.run_salmon_counter(video_path, drop_bounding_boxes=drop_bounding_boxes, bound_line_ratio=bound_line_ratio)
            except Exception as e:
                logger.error(traceback.format_exc())
        else:
            logger.info(f"Skipping {video_path}, already processed")

    def run_salmon_counter(self, video_path, drop_bounding_boxes=False, bound_line_ratio=0.5):
        loader = VideoLoader([video_path], self.data['names'])
        counter = SalmonCounter(self.model, loader, tracking_thresh=10, save_dir=str(self.detection_dir))

        out_path = self.counts_dir #/ f"{os.uname()[1]}_salmon_counts.csv"
        counter.count(tracker='bytetrack.yaml', use_gt=False, save_vid=False, save_txt=True, 
                stream_write=True, output_csv_dir=str(out_path),drop_bounding_boxes=drop_bounding_boxes, bound_line_ratio=bound_line_ratio)

def main(args):
    if args.test:
        site_save_path = DRIVE_DIR
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        site_save_path = os.path.join(DRIVE_DIR, orgid, site_name, device_id)

    vids_path = Path(site_save_path) / MOTION_DIR_NAME
    detection_dir = Path(site_save_path) / DETECTION_DIR_NAME
    counts_dir = Path(site_save_path) / COUNTS_DIR_NAME
    logs_dir = Path(site_save_path) / LOGS_DIR_PATH

    detection_dir.mkdir(exist_ok=True)
    counts_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True, parents=True)
    video_handler = VideoHandler(detection_dir, counts_dir, args.weights)

    timestamp = datetime.datetime.now().strftime("%Y%m%d")
    file_handler = logging.FileHandler(logs_dir / f"salmoncount_logs_{timestamp}.txt")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    rootlogger.addHandler(file_handler)

    current_time = time.time()

    # Initial check of all existing videos
    for filename in os.listdir(str(vids_path)):
        video_file = vids_path / filename
        modif_time = video_file.stat().st_mtime
        if current_time - modif_time > args.time_window:
            video_handler.process_video(video_file, drop_bounding_boxes=args.drop_bbox, bound_line_ratio=args.bound_line)
        else:
            logger.info(f"Ignoring recently modified video: {video_file}")
    
    # Schedule watchdog observer
    #logger.info("Starting observer...")
    #observer = Observer()
    #observer.schedule(video_handler, str(vids_path), recursive=False)
    #observer.start()

    #try:
    #    while True:
    #        time.sleep(10)
    #except KeyboardInterrupt:
    #    observer.stop()
    #observer.join()

    logger.info("Waiting a little before ending...")
    rootlogger.handlers[0].flush()
    time.sleep(30)
    logger.info("Ending...")
    rootlogger.handlers[0].flush()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use site save path")
    parser.add_argument('--weights', default='config/salmoncount.engine', help='Path to YOLO weights to load.')
    parser.add_argument('--time-window', default=4 * 60, help='The time window to ignore potentially still writing files in seconds.')
    parser.add_argument('--drop-bbox', action='store_true', help='Set this flag to determine whether the top-view boxes should be removed when calculating the counts.')
    parser.add_argument('--bound-line', default=0.5, help='Determine where the middle line is.')
    args = parser.parse_args()

    main(args)

