#!/usr/bin/env python3

import os
import argparse
import ffmpeg
from pathlib import Path
from pysalmcount import utils

EXT = '.mp4'

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

def reencode_h264(filepath):
    input_path = Path(filepath)
    tmp_filename = input_path.stem + '_tmp' + EXT
    tmp_out_path = input_path.with_name(tmp_filename)
    ffmpeg.input(filepath).output(tmp_out_path, vcodec='libx264', movflags='faststart').run()

    # Overwrite old vid file

def main(args):
    for filename in os.listdir(args.input):
        # Check if metadata file exists
        # Check if video file is not H264
        # Re-encode video to H264
        gen_metadata(filename)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-encodes video clips in a folder to H264 and re-generates their metadata.")
    parser.add_argument("input", help="Input folder")
    args = parser.parse_args()

    main(args)
