#!/usr/bin/env python3

import os
import argparse
import ffmpeg
import json
import logging
from pathlib import Path
from dataclasses import asdict

from pysalmcount import utils
from pysalmcount.motion_detect_stream import VideoSaver
from pysalmcount.motion_detect_stream import MOTION_VIDS_METADATA_DIR
import shutil

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)

logger = logging.getLogger(__name__)

EXT = '.mp4'
ARCHIVE_DIR = 'motion_vids_archive'

def gen_metadata(filepath: Path):
    metadata = utils.get_video_metadata(filepath)
    if metadata is not None:
        logger.info(f"Metadata for video file {filepath}: {metadata}")
        metadata_filepath = VideoSaver.filename_to_metadata_filepath(filepath)
        logger.info(f"Saving metadata file to harddrive: {str(metadata_filepath)}")
        with open(str(metadata_filepath), 'w') as f:
            json.dump(asdict(metadata), f)
    else:
        logger.error(f"Could not generate metadata for file: {filepath}")

def reencode_h264(filepath: Path, archive_dir: str):
    temp_path = filepath.with_name(filepath.stem + '_temp' + filepath.suffix) 
    archive_path = Path(archive_dir) / filepath.name

    ffmpeg.input(str(filepath)).output(str(temp_path), vcodec='libx264', movflags='faststart').run()
    shutil.move(filepath, archive_path)
    shutil.move(temp_path, filepath)

def main(args):
    input_dir_path = Path(args.input)
    archive_path = input_dir_path.parent / ARCHIVE_DIR
    archive_path.mkdir(exist_ok=True)
    metadata_dir = input_dir_path.parent / MOTION_VIDS_METADATA_DIR
    metadata_dir.mkdir(exist_ok=True)

    for filepath in input_dir_path.iterdir():
        try:
            if not filepath.is_file():
                continue

            metadata = utils.get_video_metadata(filepath)
        except Exception as e:
            logger.error(f'Cannot get metadata of {filepath}. Error: {e}')
            continue

        try:
            is_h264 = False
            if metadata.codec_name != 'h264':
                # Re-encode video to H264
                    reencode_h264(filepath, archive_path)
            else:
                is_h264 = True
        except Exception as e:
            logger.error(f'Cannot re-encode {filepath}. Error: {e}')
            continue

        metadata_path = metadata_dir / (filepath.stem + '.json')
        if not is_h264 or not metadata_path.exists():
            try:
                gen_metadata(filepath)
            except Exception as e:
                logger.error(f'Cannot generate metadata for {filepath}. Error: {e}')
                continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-encodes video clips in a folder to H264 and re-generates their metadata.")
    parser.add_argument("input", help="Input folder")
    args = parser.parse_args()

    main(args)
