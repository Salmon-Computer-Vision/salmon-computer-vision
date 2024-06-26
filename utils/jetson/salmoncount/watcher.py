#!/usr/bin/env python3
import os
import argparse
import time
from pathlib import Path
import subprocess
import pickle
import yaml
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)

logger = logging.getLogger(__name__)

buffered_handler = BufferedHandler(buffer_size=50)
logger.addHandler(buffered_handler)

DRIVE_DIR = Path("/app/drive/hdd")
MOTION_DIR_NAME = "motion_vids"
DETECTION_DIR_NAME = "detections"
COUNTS_DIR_NAME = "counts"
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
    def __init__(self, processed_videos, detection_dir, counts_dir, weights_path):
        self.model = YOLO(weights_path)
        self.processed_videos = processed_videos
        self.detection_dir = detection_dir
        self.counts_dir = counts_dir

        with open(CONFIG_PATH, 'r') as file:
            self.data = yaml.safe_load(file)

    def on_created(self, event):
        logger.info("New file event")
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
            self.run_salmon_counter(video_path)
            self.processed_videos.add(video_path.name)
            save_processed_videos(self.processed_videos)
        else:
            logger.info(f"Skipping {video_path}, detection already exists")

    def run_salmon_counter(self, video_path):
        loader = VideoLoader([video_path], self.data['names'])
        counter = SalmonCounter(self.model, loader, tracking_thresh=10, save_dir=str(self.detection_dir))

        out_path = self.counts_dir / f"{os.uname()[1]}_salmon_counts.csv"
        try:
            counter.count(tracker='bytetrack.yaml', use_gt=False, save_vid=False, save_txt=True, 
                    stream_write=True, output_csv=str(out_path))
        except Exception as e:
            logger.info(e)

def main(args):
    processed_videos = load_processed_videos()

    if args.test:
        site_save_path = DRIVE_DIR
    else:
        orgid, site_name, device_id = get_orgid_and_site_name(os.uname()[1])
        site_save_path = os.path.join(DRIVE_DIR, orgid, site_name, device_id)

    vids_path = Path(site_save_path) / MOTION_DIR_NAME
    detection_dir = Path(site_save_path) / DETECTION_DIR_NAME
    counts_dir = Path(site_save_path) / COUNTS_DIR_NAME

    detection_dir.mkdir(exist_ok=True)
    counts_dir.mkdir(exist_ok=True)
    video_handler = VideoHandler(processed_videos, detection_dir, counts_dir, args.weights)

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
    logger.handlers[0].flush()
    time.sleep(30)
    logger.info("Ending...")
    logger.handlers[0].flush()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("--test", action='store_true', help="Set this flag to not use site save path")
    parser.add_argument('--weights', default='config/salmoncount.engine', help='Path to YOLO weights to load.')
    args = parser.parse_args()

    main(args)

