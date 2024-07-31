#!/usr/bin/env python3

import os
import argparse
from pysalmcount import utils

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

def main(args):
    for filename in os.listdir(args.input):
        gen_metadata(filename)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-encodes video clips in a folder to H264 and re-generates their metadata.")
    parser.add_argument("input", help="Input folder")
    args = parser.parse_args()

    main(args)
