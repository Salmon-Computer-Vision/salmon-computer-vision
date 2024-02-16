#!/usr/bin/env python3
import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
from threading import Thread, Event, Lock

class VideoSaver(Thread):
    def __init__(self, buffer, folder, stop_event, lock, fps=20.0, resolution=(640, 480)):
        Thread.__init__(self)
        self.buffer = buffer  # This will be a shared queue
        self.folder = folder
        self.stop_event = stop_event  # This will signal when to stop recording
        self.lock = lock  # This will ensure thread-safe access to the buffer
        self.fps = fps
        self.resolution = resolution
        self.daemon = True

    def run(self):
        filename = get_output_filename(self.folder)
        out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'mp4v'), self.fps, self.resolution)
        
        # Write the pre-motion frames
        while self.buffer:
            with self.lock:
                frame = self.buffer.popleft()  # Safely pop from the left of the deque
            out.write(frame)

        # Continue recording until stop_event is set
        while not self.stop_event.is_set():
            with self.lock:
                if self.buffer:
                    frame = self.buffer.popleft()
                    out.write(frame)

        out.release()

def detect_motion(fg_mask, min_area=500):
    """
    Detect motion in the foreground mask by looking for contours with an area larger than min_area.
    """
    # Find contours in the fg_mask
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter out small contours
    for contour in contours:
        if cv2.contourArea(contour) > min_area:
            return True
    return False

def read_rtsp_url(file_path):
    """Read RTSP URL from the specified file."""
    with open(file_path, 'r') as file:
        return file.readline().strip()

def get_output_filename(folder):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(folder, f"motion_{timestamp}.mp4")
    return filename

def save_clip(buffer, folder, fps=10.0, resolution=(1920, 1080)):
    """Save the buffered frames as a video clip."""
    filename = get_output_filename(folder)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, resolution)
    for frame in buffer:
        out.write(frame)
    out.release()

def main(rtsp_file_path, save_folder, fps=10.0):
    rtsp_url = read_rtsp_url(rtsp_file_path)
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Error: Could not open video stream.")
        exit()

    bgsub = cv2.bgsegm.createBackgroundSubtractorCNT()
    buffer_length = 100  # Adjust based on the fps to cover desired seconds before and after motion
    buffer = deque(maxlen=buffer_length)
    motion_detected = False
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    stop_event = Event()
    lock = Lock()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Apply MOG2 algorithm to get the foreground mask
        fg_mask = bgsub.apply(frame)
        # Apply a threshold to the foreground mask to get rid of noise
        _, fg_mask = cv2.threshold(fg_mask, 25, 255, cv2.THRESH_BINARY)

        # Apply morphological operations to clean up the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        # Now detect motion
        has_motion = detect_motion(fg_mask, min_area=2000)

        # Check for motion
        if has_motion:
            if not motion_detected:
                print("Motion detected.")
                motion_detected = True
                # Signal that we need to start saving the clip
                stop_event.clear()
                video_saver = VideoSaver(buffer, save_folder, stop_event, lock)
                video_saver.start()
            else:
                # Keep adding frames to the buffer; the video saver thread will pick them up
                with lock:
                    buffer.append(frame)
        else:
            # If motion has stopped and we have a video saver running, set the stop event
            if motion_detected and not stop_event.is_set():
                print("Stopping recording.")
                stop_event.set()
                motion_detected = False

    cap.release()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Salmon Motion Detection and Video Clip Saving")
    parser.add_argument("rtsp_file_path", help="Path to the file containing the RTSP URL")
    parser.add_argument("save_folder", help="Folder where video clips will be saved")
    args = parser.parse_args()

    if not os.path.exists(args.save_folder):
        os.makedirs(args.save_folder)

    main(args.rtsp_file_path, args.save_folder)

