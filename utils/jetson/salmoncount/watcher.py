#!/usr/bin/env python3
import os
import argparse
import time
from pathlib import Path
import subprocess
import pickle
import yaml
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pysalmcount.videoloader import VideoLoader
from pysalmcount.salmon_counter import SalmonCounter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)

logger = logging.getLogger(__name__)

DRIVE_DIR = Path("/app/drive")
MOTION_DIR_NAME = "motion_vids"
DETECTION_DIR_NAME = "detections"
CONFIG_PATH = Path("/app/config/2023_combined_salmon.yaml")
PROCESSED_FILE = Path("/app/processed_videos.pkl")

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

def run_salmon_counter(video_path, detection_dir, weights_path):
    with open(CONFIG_PATH, 'r') as file:
        data = yaml.safe_load(file)
    loader = VideoLoader([video_path], data['names'])
    counter = SalmonCounter(weights_path, loader, tracking_thresh=10, save_dir=str(detection_dir))

    out_path = detection_dir / "summary" / "salmon_counts.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        counter.count(tracker='bytetrack.yaml', use_gt=False, save_vid=False, save_txt=True, 
                stream_write=True, output_csv=str(out_path))
    except Exception as e:
        logger.info(e)

class VideoHandler(FileSystemEventHandler):
    def __init__(self, processed_videos, detection_dir, weights_path):
        self.processed_videos = processed_videos
        self.detection_dir = detection_dir
        self.weights_path = weights_path

    def on_created(self, event):
        if event.src_path.endswith(".mp4"):
            video_path = Path(event.src_path)
            if video_path.name not in self.processed_videos:
                if self.is_fully_written(video_path):
                    self.process_video(video_path)
                else:
                    logger.info(f"File {video_path} is still being written.")
            else:
                logger.info(f"Skipping {video_path}, already processed")

    def is_fully_written(self, file_path, wait_time=5, check_interval=1):
        """Check if the file is fully written by monitoring its size."""
        initial_size = -1
        while True:
            current_size = file_path.stat().st_size
            if current_size == initial_size:
                return True
            initial_size = current_size
            time.sleep(check_interval)
    
    def process_video(self, video_path):
        detection_file = self.detection_dir / video_path.stem
        if not detection_file.exists():
            logger.info(f"Processing {video_path}")
            run_salmon_counter(video_path, self.detection_dir, self.weights_path)
            self.processed_videos.add(video_path.name)
            save_processed_videos(self.processed_videos)
        else:
            logger.info(f"Skipping {video_path}, detection already exists")

def main(args):
    processed_videos = load_processed_videos()

    if args.test:
        site_save_path = DRIVE_DIR
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        site_save_path = os.path.join(args.save_folder, orgid, site_name, device_id)

    vids_path = Path(site_save_path) / MOTION_DIR_NAME
    detection_dir = Path(site_save_path) / DETECTION_DIR_NAME

    video_handler = VideoHandler(processed_videos, detection_dir, args.weights)

    # Initial check of all existing videos
    for video_file in vids_path.glob('*.mp4'):
        if video_file.name not in processed_videos:
            if video_handler.is_fully_written(video_file):
                video_handler.process_video(video_file)
            else:
                logger.info(f"File {video_file} is still being written.")
        else:
            logger.info(f"Skipping {video_file}, already processed")
    
    # Schedule watchdog observer
    observer = Observer()
    observer.schedule(video_handler, str(vids_path), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use site save path")
    parser.add_argument('--weights', default='config/salmoncount.engine', help='Path to YOLO weights to load.')
    args = parser.parse_args()

    main(args)

