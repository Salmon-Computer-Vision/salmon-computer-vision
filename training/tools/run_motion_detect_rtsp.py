#!/usr/bin/env python3
from pysalmcount import videoloader as vl
from pysalmcount import motion_detect_stream as md
import argparse

def read_rtsp_url(self, file_path):
    """Read RTSP URL from the specified file."""
    with open(file_path, 'r') as file:
        return file.readline().strip()

def main(rtsp_file_path, save_folder):
    rtsp_url = self.read_rtsp_url(rtsp_file_path)

    vidloader = vl.VideoLoader([rtsp_url])
    det = md.MotionDetector(vidloader, save_folder)
    det.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("rtsp_file_path", help="Path to the file containing the RTSP URL")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    args = parser.parse_args()

    if not os.path.exists(args.save_folder):
        os.makedirs(args.save_folder)

    main(args.rtsp_file_path, args.save_folder)

