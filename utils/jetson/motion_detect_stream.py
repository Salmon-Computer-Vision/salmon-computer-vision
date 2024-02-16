#!/usr/bin/env python3
import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os

def read_rtsp_url(file_path):
    """Read RTSP URL from the specified file."""
    with open(file_path, 'r') as file:
        return file.readline().strip()

def save_clip(buffer, folder, fps=20.0, resolution=(640, 480)):
    """Save the buffered frames as a video clip."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(folder, f"motion_{timestamp}.avi")
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(filename, fourcc, fps, resolution)
    for frame in buffer:
        out.write(frame)
    out.release()

def main(rtsp_file_path, save_folder):
    rtsp_url = read_rtsp_url(rtsp_file_path)
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Error: Could not open video stream.")
        exit()

    mog2 = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
    buffer_length = 100  # Adjust based on the fps to cover desired seconds before and after motion
    buffer = deque(maxlen=buffer_length)
    motion_detected = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Apply MOG2 algorithm to get the foreground mask
        fg_mask = mog2.apply(frame)
        # Check for motion
        if np.any(fg_mask > 0):  # Change this threshold as needed
            if not motion_detected:
                print("Motion detected.")
                motion_detected = True
            buffer.append(frame)
        elif motion_detected:
            # Save the clip when motion stops
            print("Saving clip.")
            save_clip(buffer, save_folder)
            buffer.clear()
            motion_detected = False
        else:
            # No motion, manage buffer for pre-motion frames
            buffer.append(frame)

    cap.release()
    if motion_detected:
        # Ensure the last clip is saved if the program ends and motion was detected
        save_clip(buffer, save_folder)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("rtsp_file_path", help="Path to the file containing the RTSP URL")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    args = parser.parse_args()

    if not os.path.exists(args.save_folder):
        os.makedirs(args.save_folder)

    main(args.rtsp_file_path, args.save_folder)

