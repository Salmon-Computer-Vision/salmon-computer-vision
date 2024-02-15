#!/usr/bin/env python3
import os
import cv2
from concurrent.futures import ThreadPoolExecutor
import argparse
import pandas as pd

def extract_frames(input_base_dir, video_path, output_base_dir, frame_rate):
    """
    Extracts frames from a video file at a specified frame rate.
    :param video_path: Path to the video file.
    :param output_base_dir: Base directory to store the extracted frames, preserving the input file structure.
    :param frame_rate: Rate at which frames should be extracted (every 'frame_rate' frames).
    """
    try:
        # Open the video file
        vidcap = cv2.VideoCapture(video_path)
        success, image = vidcap.read()
        count = 0
        frame_id = 0

        # Create output directory for the current video
        relative_path = os.path.relpath(video_path, start=input_base_dir)
        output_dir = os.path.join(output_base_dir, os.path.splitext(relative_path)[0])
        os.makedirs(output_dir, exist_ok=True)
        print(video_path, 'to', output_dir)

        while success:
            if count % frame_rate == 0:
                # Save frame as JPEG file
                frame_file = os.path.join(output_dir, f"{frame_id:07d}.png")
                cv2.imwrite(frame_file, image)
                frame_id += 1
            success, image = vidcap.read()
            count += 1

    except Exception as e:
        print(f"Error extracting frames from video {video_path}: {e}")

# Function to read CSV and filter out the required video file paths
def get_video_file_paths(csv_path):
    try:
        # Read the CSV file into a DataFrame
        df = pd.read_csv(csv_path)

        # Filter rows where "Annotate Status" is "Completed"
        completed_videos = df[df["Annotate Status"] == "Completed"]

        # Combine "File Path" and "File Name" to form the full video file path
        completed_videos['Video Path'] = completed_videos['File Path'].str.cat(completed_videos['File Name'], sep='')

        # Return the filtered list of video file paths
        return completed_videos['Video Path'].tolist()
    except Exception as e:
        raise Exception(f"An error occurred while processing the CSV file: {e}")

def find_videos(input_dir):
    """
    Recursively searches for all video files within a given directory.
    :param input_dir: Directory to search within.
    :return: Generator of file paths to each video file found.
    """
    for subdir, dirs, files in os.walk(input_dir):
        for filename in files:
            if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                yield os.path.join(subdir, filename)

def main(input_base_dir, csv_path, output_base_dir, frame_rate, max_workers):
    """
    Main function to extract frames from all videos found in the given directory.
    :param input_base_dir: Input directory containing video files.
    :param output_base_dir: Output directory to store the extracted frames.
    :param frame_rate: Rate at which frames should be extracted from the videos.
    :param max_workers: Maximum number of threads to use for parallel processing.
    """
    #videos = list(find_videos(input_base_dir))
    videos = get_video_file_paths(csv_path)

    # Process each video in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for video_path in videos:
            executor.submit(extract_frames, input_base_dir, video_path, output_base_dir, frame_rate)

# Command-line interface setup
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract frames from videos in parallel using Datumaro.')
    parser.add_argument('input_directory', help='Input directory containing the video files')
    parser.add_argument('csv_path', help='Input CSV file describing the video file paths')
    parser.add_argument('output_directory', help='Output directory to store the extracted frames')
    parser.add_argument('--frame-rate', type=int, default=1,
                        help='Frame rate to extract frames (e.g., --frame-rate 1 to extract all frames).')
    parser.add_argument('--workers', type=int, default=os.cpu_count(),
                        help='Maximum number of threads to use. Defaults to the number of CPU cores if not set.')
    args = parser.parse_args()

    main(args.input_directory, args.csv_path, args.output_directory, args.frame_rate, args.workers)
