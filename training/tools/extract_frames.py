#!/usr/bin/env python3
import os
import cv2
from concurrent.futures import ThreadPoolExecutor
import argparse
import pandas as pd
from pathlib import Path

def extract_frames(input_base_dir, video_path, output_base_dir, frame_rate):
    """
    Extracts frames from a video file at a specified frame rate.
    :param video_path: Path to the video file.
    :param output_base_dir: Base directory to store the extracted frames, preserving the input file structure.
    :param frame_rate: Rate at which frames should be extracted (every 'frame_rate' frames).
    """
    try:
        # Create output directory for the current video
        relative_path = os.path.relpath(video_path, start=input_base_dir)
        output_dir = os.path.join(output_base_dir, os.path.splitext(relative_path)[0])
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(video_path, 'to', output_dir)
            
            # Open the video file
            video_path = os.path.join(input_base_dir, video_path)
            vidcap = cv2.VideoCapture(video_path)
            success, image = vidcap.read()
            count = 0
            frame_id = 0
    
            while success:
                if count % frame_rate == 0:
                    # Save frame as JPEG file
                    frame_file = os.path.join(output_dir, f"{frame_id:07d}.png")
                    cv2.imwrite(frame_file, image)
                    frame_id += 1
                success, image = vidcap.read()
                count += 1

        symlink_dir = f'{output_base_dir}_symlink'
        os.makedirs(symlink_dir, exist_ok=True)
        os.symlink(os.path.abspath(output_dir), os.path.join(symlink_dir, os.path.basename(os.path.splitext(relative_path)[0])))

    except Exception as e:
        print(f"Error extracting frames from video {video_path}: {e}")

def process_filepaths(input_file):
    # Dictionary to hold filename without extension as key, and list of full filepaths as values
    filepath_dict = {}

    with open(input_file, 'r') as file:
        for line in file:
            # Strip newline and whitespace
            path = line.strip()
            # Extract filename without extension
            filename_without_ext = os.path.splitext(os.path.basename(path))[0]
            if filename_without_ext in filepath_dict:
                filepath_dict[filename_without_ext].append(path)
            else:
                filepath_dict[filename_without_ext] = [path]

    # Filter duplicates by preferring 'MotionDet' in the filepath
    filtered_filepaths = []
    for paths in filepath_dict.values():
        if len(paths) > 1:
            # Sort paths to prioritize one with 'MotionDet'
            paths.sort(key=lambda x: 'MotionDet' not in x)
        # Only add the most preferred path (handles single and multiple paths)
        filtered_filepaths.append(paths[0])

    return filtered_filepaths
    
def intersect_filepaths_with_filenames(filepaths, filenames):
    # Convert the list of filenames into a set for O(1) lookup
    filenames_set = set(filenames)

    # Extract the basename (filename) from each filepath and check if it exists in the filenames set
    # os.path.basename is used to get the filename from a filepath
    intersected_filepaths = [path for path in filepaths if Path(path).stem in filenames_set]

    return intersected_filepaths

# Function to read CSV and filter out the required video file paths
def get_video_file_paths(csv_path, text_file, filter_file):
    try:
        if text_file:
            vid_paths = process_filepaths(csv_path)
        else:
            # Read the CSV file into a DataFrame
            df = pd.read_csv(csv_path)
    
            # Filter rows where "Annotate Status" is "Completed"
            completed_videos = df.copy()
    
            # Combine "File Path" and "File Name" to form the full video file path
            completed_videos.loc[:, 'Video Path'] = completed_videos['File Path'].str.cat(completed_videos['File Name'], sep='/')

            vid_paths = completed_videos['Video Path'].tolist()
            
        if filter_file:
            with open(filter_file, 'r') as file:
                filter_filenames = [
                    str(Path(line.strip()).parent.stem) if str(Path(line.strip()).parent).endswith('.json') else str(Path(line.strip()).parent.name)
                    for line in file if line.strip()
                ]

            # Filter the original list to keep only file paths with remaining base names
            vid_paths = intersect_filepaths_with_filenames(vid_paths, filter_filenames)
        # Return the filtered list of video file paths
        return vid_paths
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

def main(args):
    """
    Main function to extract frames from all videos found in the given directory.
    :param input_base_dir: Input directory containing video files.
    :param output_base_dir: Output directory to store the extracted frames.
    :param frame_rate: Rate at which frames should be extracted from the videos.
    :param max_workers: Maximum number of threads to use for parallel processing.
    """
    #videos = list(find_videos(input_base_dir))
    videos = get_video_file_paths(args.csv_path, args.text_file, args.filter_file)

    # Process each video in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for video_path in videos:
            executor.submit(extract_frames, args.input_directory, video_path, args.output_directory, args.frame_rate)

# Command-line interface setup
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract frames from videos in parallel.')
    parser.add_argument('input_directory', help='Input directory containing the video files')
    parser.add_argument('csv_path', help='Input CSV file describing the video file paths')
    parser.add_argument('output_directory', help='Output directory to store the extracted frames')
    parser.add_argument('--text-file', action='store_true', help='Turns the csv_path into a text file with paths. Best to use with --filter-file.')
    parser.add_argument('--filter-file', default=None, help='Input text file to filter the video file paths')
    parser.add_argument('--frame-rate', type=int, default=1,
                        help='Frame rate to extract frames (e.g., --frame-rate 1 to extract all frames).')
    parser.add_argument('--workers', type=int, default=os.cpu_count(),
                        help='Maximum number of threads to use. Defaults to the number of CPU cores if not set.')
    args = parser.parse_args()

    main(args)
