#!/usr/bin/env python3

import os
import argparse
import ffmpeg
import json
from pathlib import Path

from pysalmcount import utils
from pysalmcount.motion_detect_stream import VideoSaver
from pysalmcount.motion_detect_stream import MOTION_VIDS_METADATA_DIR
import shutil

EXT = '.mp4'
ARCHIVE_DIR = 'motion_vids_archive'

def gen_metadata(filename):
    metadata = utils.get_video_metadata(filename)
    if metadata is not None:
        logger.info(f"Metadata for video file {filename}: {metadata}")
        metadata_filepath = VideoSaver.filename_to_metadata_filepath(Path(filename))
        logger.info(f"Saving metadata file to harddrive: {str(metadata_filepath)}")
        with open(str(metadata_filepath), 'w') as f:
            json.dump(asdict(metadata), f)
    else:
        logger.error(f"Could not generate metadata for file: {filename}")

def reencode_h264(filename: str, archive_dir: str):
    filepath = Path(filename)
    archive_path = Path(archive_dir) / filepath.name
    shutil.move(filepath, archive_path)

    ffmpeg.input(archive_path).output(filepath, vcodec='libx264', movflags='faststart').run()

def main(args):
    input_dir_path = Path(args.input)
    archive_path = input_dir_path.parent / ARCHIVE_DIR
    archive_path.mkdir(exist_ok=True)

    for filename in os.listdir(args.input):
        filepath = Path(filename)
        metadata = utils.get_video_metadata(filename)

        is_h264 = False
        if metadata.codec_name != 'h264':
            # Re-encode video to H264
            reencode_h264(filename, archive_path)
        else:
            is_h264 = True

        metadata_path = filepath.parent / MOTION_VIDS_METADATA_DIR / (filepath.stem + '.json')
        if not is_h264 or not metadata_path.exists():
            gen_metadata(filename)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-encodes video clips in a folder to H264 and re-generates their metadata.")
    parser.add_argument("input", help="Input folder")
    args = parser.parse_args()

    main(args)
