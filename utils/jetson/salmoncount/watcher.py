#!/usr/bin/env python3
import os
import time
from pathlib import Path
import subprocess
import pickle
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VIDEO_DIR = Path("/app/videos")
DETECTION_DIR = Path("/app/detections")
CONFIG_PATH = Path("/app/config/2023_combined_salmon.yaml")
WEIGHTS_PATH = Path("/app/config/weights/best.pt")
PROCESSED_FILE = Path("/app/processed_videos.pkl")

def load_processed_videos():
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, 'rb') as f:
            return pickle.load(f)
    return set()

def save_processed_videos(processed_videos):
    with open(PROCESSED_FILE, 'wb') as f:
        pickle.dump(processed_videos, f)

def run_salmon_counter(video_path):
    annotation_list_path = video_path.with_suffix('.txt')
    csv_output_path = DETECTION_DIR / (video_path.stem + '_counts.csv')
    
    cmd = [
        'python3', 'salmon_counter.py',
        str(video_path),
        str(annotation_list_path),
        str(csv_output_path),
        '--weights', str(WEIGHTS_PATH),
        '--device', '0',
        '--format', 'video'
    ]
    
    subprocess.run(cmd)

class VideoHandler(FileSystemEventHandler):
    def __init__(self, processed_videos):
        self.processed_videos = processed_videos

    def on_created(self, event):
        if event.src_path.endswith(".mp4"):
            video_path = Path(event.src_path)
            if video_path.name not in self.processed_videos:
                if self.is_fully_written(video_path):
                    self.process_video(video_path)
                else:
                    print(f"File {video_path} is still being written.")
            else:
                print(f"Skipping {video_path}, already processed")

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
        detection_file = DETECTION_DIR / (video_path.stem + '_counts.csv')
        if not detection_file.exists():
            print(f"Processing {video_path}")
            run_salmon_counter(video_path)
            self.processed_videos.add(video_path.name)
            save_processed_videos(self.processed_videos)
        else:
            print(f"Skipping {video_path}, detection already exists")

def main():
    processed_videos = load_processed_videos()
    video_handler = VideoHandler(processed_videos)

    # Initial check of all existing videos
    for video_file in VIDEO_DIR.glob('*.mp4'):
        if video_file.name not in processed_videos:
            if video_handler.is_fully_written(video_file):
                video_handler.process_video(video_file)
            else:
                print(f"File {video_file} is still being written.")
        else:
            print(f"Skipping {video_file}, already processed")
    
    # Schedule watchdog observer
    observer = Observer()
    observer.schedule(video_handler, str(VIDEO_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()

