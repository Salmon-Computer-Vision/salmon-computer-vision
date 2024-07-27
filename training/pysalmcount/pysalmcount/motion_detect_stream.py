#!/usr/bin/env python3
from .dataloader import DataLoader

import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
import errno
from threading import Thread, Event, Lock, Condition
import logging
import time
from pathlib import Path
import json
from dataclasses import asdict

from pysalmcount import utils

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)
logger = logging.getLogger(__name__)

gst_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert ! video/x-raw,format=BGRx ! nvvidconv ! nvv4l2h264enc vbv-size=200000 bitrate=3000000 insert-vui=1 ! h264parse ! mp4mux ! filesink location="
gst_raspi_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert !  v4l2h264enc extra-controls=encode,video_bitrate=3000000 ! h264parse ! qtmux ! filesink location="
MOTION_VIDS_METADATA_DIR = 'motion_vids_metadata'

class VideoSaver(Thread):
    def __init__(self, buffer, folder, stop_event, lock, condition, fps=10.0, resolution=(640, 480), 
            orin=False, raspi=False, save_prefix=None):
        Thread.__init__(self)
        self.buffer = buffer  # This will be a shared queue
        self.folder = folder
        self.stop_event = stop_event  # This will signal when to stop recording
        self.lock = lock  # This will ensure thread-safe access to the buffer
        self.condition = condition
        self.fps = fps
        self.resolution = resolution
        self.gst_out = 'appsrc ! videoconvert ! x264enc ! mp4mux ! filesink location='
        self.orin = orin
        self.raspi = raspi
        self.save_prefix = save_prefix

    @staticmethod
    def get_output_filename(folder, suffix='_M', save_prefix=None):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_prefix is None:
            save_prefix = os.uname()[1]
        filename = os.path.join(folder, f"{save_prefix}_{timestamp}{suffix}.mkv")
        return filename

    @staticmethod
    def filename_to_metadata_filepath(filename: Path) -> Path:
        metadata_dir = filename.parent.parent / MOTION_VIDS_METADATA_DIR
        metadata_dir.mkdir(exist_ok=True)
        return metadata_dir / f"{filename.stem}.json"

    def run(self):
        filename = VideoSaver.get_output_filename(self.folder, save_prefix=self.save_prefix)

        logger.info(f"Writing motion video to {filename}")
        if self.orin:
            out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*"h264"), self.fps, self.resolution)
        else:
            gst_writer = gst_writer_str
            if self.raspi:
                logger.info("Writing with raspi hardware...")
                gst_writer = gst_raspi_writer_str
            out = cv2.VideoWriter(gst_writer + filename, cv2.CAP_GSTREAMER, 0, self.fps, self.resolution)
        
        c = 0
        # Write the pre-motion frames
        while self.buffer:
            if c % 20 == 0:
                logger.info(f'Saving pre... {c}')
            with self.lock:
                frame = self.buffer.popleft()  # Safely pop from the left of the deque
            out.write(frame)
            c += 1

        c = 0
        # Continue recording until stop_event is set
        while not self.stop_event.is_set():
            with self.condition:
                if not self.buffer:
                    if not self.stop_event.is_set():
                        # Wait for a signal that a new frame is available or stop_event is set
                        self.condition.wait()
                #self.condition.wait_for(lambda: self.buffer or self.stop_event.is_set())

            if self.buffer:
                with self.lock:
                    frame = self.buffer.popleft()
                if c % 20 == 0:
                    logger.info(f'Saving... {c}')
                out.write(frame)

            c += 1

        out.release()

        metadata = utils.get_video_metadata(filename)
        if metadata is not None:
            logger.info(f"Metadata for video file {filename}: {metadata}")
            metadata_filepath = VideoSaver.filename_to_metadata_filepath(Path(filename))
            with open(str(metadata_filepath), 'w') as f:
                json.dump(asdict(metadata), f)
            logger.info(f"Saving metadata file to harddrive: {str(metadata_filepath)}")
        else:
            logger.error(f"Could not generate metadata for file: {filename}")

class MotionDetector:
    FILENAME = 'filename'
    CLIPS = 'clips'
    def __init__(self, dataloader: DataLoader, save_folder, save_prefix=None):
        self.dataloader = dataloader
        self.save_folder = save_folder
        self.frame_log = {}
        self.save_prefix = save_prefix

    def detect_motion(self, fg_mask, min_area=500):
        """
        Detect motion in the foreground mask by looking for contours with an area larger than min_area.
        """
        # Find contours in the fg_mask
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2:]

        # Filter out small contours
        for contour in contours:
            if cv2.contourArea(contour) > min_area:
                return True
        return False

    def run(self, algo='MOG2', save_video=True, fps=None, orin=False, raspi=False):
        # Motion Detection Params
        bgsub_threshold = 50
        bgsub_min_pixelstability = 1
        bgsub_max_pixelstability = 4
        threshold_value = 50 # Increase threshold value to minimize noise
        kernel_size = (11, 11) # Increase kernel size to ignore smaller motions
        dilate_iter = 1
        erode_iter = 2 # Run multiple iterations to incrementally remove smaller objects
        min_contour_area = 10000 # Ignore contour objects smaller than this area
        MOTION_EVENTS_THRESH = 0.4 # Ratio of seconds of motion required to trigger detection
        BUFFER_LENGTH = 5 # Number of seconds before motion to keep
        MAX_CLIP = 2 * 60 # Maximum number of seconds per clip
        MAX_CONTINUOUS = 30 * 60 # Max continuous video in seconds

        cont_dir = os.path.join(self.save_folder, 'cont_vids')
        if not os.path.exists(cont_dir):
            os.mkdir(cont_dir) # Let exception be raised if recursive dir
        motion_dir = os.path.join(self.save_folder, 'motion_vids')
        if not os.path.exists(motion_dir):
            os.mkdir(motion_dir) # Let exception be raised if recursive dir

        cur_clip = self.dataloader.next_clip()
        self.frame_log[cur_clip.name] = []

        if fps is None:
            # Retrieve the FPS of the video stream
            fps = self.dataloader.fps()

        fps = int(fps)

        logger.info(f"FPS: {fps}")

        MAX_FRAMES_CLIP = int(MAX_CLIP * fps)
        MAX_CONTINUOUS_FRAMES = int(MAX_CONTINUOUS * fps)
        MOTION_EVENTS_THRESH_FRAMES = int(MOTION_EVENTS_THRESH * fps)

        if algo == 'MOG2':
            bgsub = cv2.createBackgroundSubtractorMOG2(varThreshold=bgsub_threshold, detectShadows=False)
        else:
            bgsub = cv2.bgsegm.createBackgroundSubtractorCNT(minPixelStability=bgsub_min_pixelstability, useHistory=True, maxPixelStability=bgsub_max_pixelstability)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel_size)

        warm_up = fps
        buffer_length = int(fps * BUFFER_LENGTH)  # Buffer to save before motion
        buffer = deque(maxlen=buffer_length)
        motion_detected = False

        # Concurrency-safe constructs
        stop_event = Event()
        lock = Lock()
        condition = Condition()

        delay = int(fps * 5) # Number of seconds to delay after motion
        count_delay = 0


        video_saver = None
        frame_counter = MAX_CONTINUOUS_FRAMES
        motion_counter = 0
        num_motion_events = 0
        frame_start = 0
        for item in self.dataloader.items():
            if frame_counter % fps == 0:
                start_time=time.time()
            # Constantly check if save folder exists
            if not os.path.exists(self.save_folder):
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.save_folder)

            frame = item.frame
            if isinstance(frame, str):
                frame = cv2.imread(frame)
            frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)

            if save_video:
                if frame_counter >= MAX_CONTINUOUS_FRAMES:
                    cont_filename = VideoSaver.get_output_filename(cont_dir, '_C', save_prefix=self.save_prefix)
                    logger.info(f"Writing continuous video to {cont_filename}")
                    if orin:
                        cont_vid_out = cv2.VideoWriter(cont_filename, cv2.VideoWriter_fourcc(*"h264"),
                                fps, (frame.shape[1], frame.shape[0]))
                    else:
                        gst_writer = gst_writer_str
                        if raspi:
                            logger.info("Writing with raspi hardware...")
                            gst_writer = gst_raspi_writer_str
                        cont_vid_out = cv2.VideoWriter(gst_writer + cont_filename, 
                                                       cv2.CAP_GSTREAMER, 0, fps, (frame.shape[1], frame.shape[0]))
                        logger.info(f"Created VideoWriter to {cont_filename}")
                    frame_counter = 0

                if frame_counter % fps == 0:
                    start_in_time = time.time()

                cont_vid_out.write(frame)

                if frame_counter % fps == 0:
                    end_in_time=time.time()
                    elapsed_in_time = (end_in_time - start_in_time) * 1000
                    logger.info(f"Cont save: {elapsed_in_time:.2f} ms")

            if frame_counter % fps == 0:
                start_in_time = time.time()

            # Apply background subtraction algorithm to get the foreground mask
            fg_mask = bgsub.apply(frame)

            if frame_counter % fps == 0:
                end_in_time=time.time()
                elapsed_in_time = (end_in_time - start_in_time) * 1000
                logger.info(f"BGSub: {elapsed_in_time:.2f} ms")
            #cont_vid_out.write(cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2RGB))

            if frame_counter % fps == 0:
                start_in_time = time.time()
            has_motion = False
            if warm_up <= 0:
                # Apply a threshold to the foreground mask to get rid of noise
                _, fg_mask = cv2.threshold(fg_mask, threshold_value, 255, cv2.THRESH_BINARY)

                # Apply morphological operations to clean up the mask
                fg_mask = cv2.dilate(fg_mask, None, iterations=dilate_iter) 
                fg_mask = cv2.erode(fg_mask, None, iterations=erode_iter) 

                # Now detect motion
                has_motion = self.detect_motion(fg_mask, min_area=min_contour_area)
            else:
                warm_up -= 1
            if frame_counter % fps == 0:
                end_in_time=time.time()
                elapsed_in_time = (end_in_time - start_in_time) * 1000
                logger.info(f"check motion: {elapsed_in_time:.2f} ms")

            with lock:
                buffer.append(frame)
            with condition:
                condition.notify() # Signal the VideoSaver thread that a new frame is available

            motion_counter += 1

            # Check for motion
            if has_motion:
                num_motion_events += 1
                count_delay = 0
                if not motion_detected and num_motion_events >= MOTION_EVENTS_THRESH_FRAMES:
                    logger.info(f"Motion detected with {num_motion_events} events")
                    motion_detected = True
                    motion_counter = 0
                    frame_start = frame_counter
                    if save_video:
                        # Signal that we need to start saving the clip
                        stop_event.clear()
                        video_saver = VideoSaver(buffer, motion_dir, 
                                stop_event, lock, condition, fps=fps, 
                                resolution=(frame.shape[1], frame.shape[0]),
                                orin=orin, raspi=raspi, save_prefix=self.save_prefix)
                        video_saver.start()
                else:
                    if save_video and motion_counter > MAX_FRAMES_CLIP and not stop_event.is_set():
                        logger.info("Max clip length exceeded. Motion stopped.")
                        logger.info("Stopping recording.")
                        stop_event.set()
                        with condition:
                            condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
                        motion_detected = False
            else:
                num_motion_events = 0
                if count_delay < delay:
                    count_delay += 1
                else:
                    # If motion has stopped and we have a video saver running, set the stop event
                    if motion_detected:
                        logger.info("Delay exceeded. Motion stopped.")
                        self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                        motion_counter = 0
                        if save_video and not stop_event.is_set():
                            logger.info("Stopping recording.")
                            stop_event.set()
                            with condition:
                                condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
                            motion_detected = False
                        elif not save_video:
                            motion_detected = False

            if frame_counter % fps == 0:
                end_time=time.time()
                elapsed_time = (end_time - start_time) * 1000
                logger.info(f"Time elapsed: {elapsed_time:.2f} ms")
            frame_counter += 1

        try:
            if motion_detected:
                logger.info("No more frames. Motion stopped.")
                self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                motion_counter = 0
                if save_video and not stop_event.is_set():
                    logger.info("Stopping recording.")
                    stop_event.set()
                    with condition:
                        condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
                    motion_detected = False
                elif not save_video:
                    motion_detected = False
            video_saver.join()
        except:
            pass
        return self.frame_log
