#!/usr/bin/env python3
from .dataloader import DataLoader

import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
import errno
from multiprocessing import Process, Event, Lock, Condition, Array, Value
import ctypes
import logging
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
)
logger = logging.getLogger(__name__)

gst_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert ! video/x-raw,format=BGRx ! nvvidconv ! nvv4l2h264enc vbv-size=200000 bitrate=3000000 insert-vui=1 ! h264parse ! mp4mux ! filesink location="
gst_raspi_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! v4l2convert !  v4l2h264enc extra-controls=encode,video_bitrate=3000000 ! h264parse ! mp4mux ! filesink location="

class VideoSaver(Process):
    def __init__(self, buffer, frame_shape, head, tail, buffer_length, folder, stop_event, lock, condition, fps=10.0, resolution=(640, 480), 
            orin=False, raspi=False, save_prefix=None):
        Process.__init__(self)
        self.buffer = buffer  # This will be a shared queue
        self.frame_shape = frame_shape
        self.head = head
        self.tail = tail
        self.buffer_length = buffer_length
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
        filename = os.path.join(folder, f"{save_prefix}_{timestamp}{suffix}.mp4")
        return filename

    def run(self):
        filename = VideoSaver.get_output_filename(self.folder, save_prefix=self.save_prefix)
        logger.info(f"Writing motion video to {filename}")
        if self.orin:
            out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, self.resolution)
        else:
            gst_writer = gst_writer_str
            if self.raspi:
                logger.info("Writing with raspi hardware...")
                gst_writer = gst_raspi_writer_str
            out = cv2.VideoWriter(gst_writer + filename, cv2.CAP_GSTREAMER, 0, self.fps, self.resolution)
        
        c = 0
        # Write the pre-motion frames
        while True:
            if c % 20 == 0:
                logger.info(f'Saving pre... {c}')
            with self.lock:
                if self.tail.value == self.head.value:
                    break
                frame_idx = self.tail.value % self.buffer_length
                start_idx = frame_idx * np.prod(self.frame_shape)
                frame = np.frombuffer(self.shared_frames, dtype=np.uint8, count=np.prod(self.frame_shape), offset=start_idx).reshape(self.frame_shape)
                #frame = self.buffer.pop(0)  # Safely pop from the left of the deque
                self.tail.value = (self.tail.value + 1) % self.buffer_length # Increment circularly
            out.write(frame)
            c += 1

        c = 0
        # Continue recording until stop_event is set
        while not self.stop_event.is_set():
            with self.condition:
                #if not self.buffer:
                #    if not self.stop_event.is_set():
                #        # Wait for a signal that a new frame is available or stop_event is set
                #        self.condition.wait()
                self.condition.wait_for(lambda: self.tail.value != self.head.value or self.stop_event.is_set())

            with self.lock:
                if self.tail.value != self.head.value:
                    frame_idx = self.tail.value % self.buffer_length
                    start_idx = frame_idx * np.prod(self.frame_shape)
                    frame = np.frombuffer(self.shared_frames, dtype=np.uint8, count=np.prod(self.frame_shape), offset=start_idx).reshape(self.frame_shape)
                    #frame = self.buffer.pop(0)
                    self.tail.value = (self.tail.value + 1) % self.buffer_length # Increment circularly

            if c % 20 == 0:
                logger.info(f'Saving... {c}')
            out.write(frame)

            c += 1

        out.release()

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
        threshold_value = 50 # Increase threshold value to minimize noise
        kernel_size = (7, 7) # Increase kernel size to ignore smaller motions
        morph_iterations = 1 # Run multiple iterations to incrementally remove smaller objects
        min_contour_area = 2000 # Ignore contour objects smaller than this area
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
            bgsub = cv2.bgsegm.createBackgroundSubtractorCNT(minPixelStability=int(fps), maxPixelStability=int(fps*60))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel_size)

        warm_up = fps
        buffer_length = int(fps * BUFFER_LENGTH)  # Buffer to save before motion
        #manager = Manager()
        #buffer = manager.list()
        frame_shape = (self.dataloader.video_size()[0], self.dataloader.video_size()[1], 3)
        buffer = Array(ctypes.c_uint8, range(buffer_length * np.prod(frame_shape)), lock=False)
        head = Value('i', 0)
        tail = Value('i', 0)

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
            start_time=time.time()
            # Constantly check if save folder exists
            if not os.path.exists(self.save_folder):
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.save_folder)

            frame = item.frame

            if save_video:
                if frame_counter >= MAX_CONTINUOUS_FRAMES:
                    cont_filename = VideoSaver.get_output_filename(cont_dir, '_C', save_prefix=self.save_prefix)
                    logger.info(f"Writing continuous video to {cont_filename}")
                    if orin:
                        cont_vid_out = cv2.VideoWriter(cont_filename, cv2.VideoWriter_fourcc(*"mp4v"),
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

                start_cont_time = time.time()
                cont_vid_out.write(frame)
                end_cont_time = time.time()
                if frame_counter % fps == 0:
                    cont_elapsed = (end_cont_time - start_cont_time) * 1000
                    logger.info(f"Cont: {cont_elapsed:.2f} ms")


            if isinstance(frame, str):
                frame = cv2.imread(frame)

            # Apply background subtraction algorithm to get the foreground mask
            start_bg_time = time.time()
            fg_mask = bgsub.apply(frame)
            end_bg_time = time.time()
            if frame_counter % fps == 0:
                bg_elapsed = (end_bg_time - start_bg_time) * 1000
                logger.info(f"BGSub: {bg_elapsed:.2f} ms")
            #cont_vid_out.write(cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2RGB))

            has_motion = False
            if warm_up <= 0:
                # Apply a threshold to the foreground mask to get rid of noise
                _, fg_mask = cv2.threshold(fg_mask, threshold_value, 255, cv2.THRESH_BINARY)

                # Apply morphological operations to clean up the mask
                start_bg_time = time.time()
                fg_mask = cv2.dilate(fg_mask, None, iterations=morph_iterations)
                #for _ in range(morph_iterations):
                #    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel) 
                end_bg_time = time.time()
                if frame_counter % fps == 0:
                    bg_elapsed = (end_bg_time - start_bg_time) * 1000
                    logger.info(f"Morph: {bg_elapsed:.2f} ms")

                # Now detect motion
                has_motion = self.detect_motion(fg_mask, min_area=min_contour_area)
            else:
                warm_up -= 1

            start_bg_time = time.time()
            with lock:
                # Increment in a circular fashion
                head.value = (head.value + 1) % buffer_length

                frame_idx = head.value % buffer_length
                start_idx = frame_idx * np.prod(frame_shape)
                np_frame = np.frombuffer(shared_frames, dtype=np.uint8, count=np.prod(frame_shape), offset=start_idx).reshape(frame_shape)
                np.copyto(np_frame, frame)
                #if len(buffer) >= buffer_length:
                #    buffer.pop(0)
                #buffer.append(frame)
            end_bg_time = time.time()
            if frame_counter % fps == 0:
                bg_elapsed = (end_bg_time - start_bg_time) * 1000
                logger.info(f"Buffer: {bg_elapsed:.2f} ms")
            with condition:
                condition.notify() # Signal the VideoSaver thread that a new frame is available

            motion_counter += 1

            # Check for motion
            if has_motion:
                num_motion_events += 1
                count_delay = 0
                if not motion_detected and num_motion_events >= MOTION_EVENTS_THRESH_FRAMES:
                    logger.info("Motion detected.")
                    motion_detected = True
                    motion_counter = 0
                    frame_start = frame_counter
                    if save_video:
                        # Signal that we need to start saving the clip
                        stop_event.clear()
                        video_saver = VideoSaver(buffer, frame_shape, head, tail, buffer_length, motion_dir, 
                                stop_event, lock, condition, fps=fps, 
                                resolution=(frame.shape[1], frame.shape[0]),
                                orin=orin, save_prefix=self.save_prefix)
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

            end_time=time.time()
            elapsed_time = (end_time - start_time) * 1000
            if frame_counter % fps == 0:
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
