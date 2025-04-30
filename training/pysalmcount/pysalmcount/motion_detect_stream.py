#!/usr/bin/env python3
from .dataloader import DataLoader

import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
import errno
#from threading import Thread, Event, Lock, Condition
from multiprocessing import shared_memory, Process, Event, Lock, Condition, Value, Array
import logging
import time
from pathlib import Path
import json
from dataclasses import asdict

from pysalmcount import utils

logger = logging.getLogger(__name__)

gst_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert ! video/x-raw,format=BGRx ! nvvidconv ! nvv4l2h264enc vbv-size=200000 bitrate=3000000 insert-vui=1 ! h264parse ! mp4mux ! filesink location="
gst_raspi_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert !  v4l2h264enc extra-controls=encode,video_bitrate=3000000 ! h264parse ! qtmux ! filesink location="
MOTION_VIDS_METADATA_DIR = 'motion_vids_metadata'
VIDEO_ENCODER = 'avc1'

class VideoSaver(Process):
    def __init__(self, shm_name, frame_shape, head: Value, tail: Value, buffer_length, folder, stop_event, lock_head, lock_tail, condition, fps=10.0,
            orin=False, raspi=False, save_prefix=None):
        super().__init__()
        self.frame_shape = frame_shape
        self.head = head
        self.tail = tail
        self.buffer_length = buffer_length
        self.folder = folder
        self.stop_event = stop_event  # This will signal when to stop recording
        self.lock_head = lock_head  # Locks the head value
        self.lock_tail = lock_tail  # Locks the tail value
        self.condition = condition
        self.fps = fps
        self.resolution = (frame_shape[1], frame_shape[0])
        self.gst_out = 'appsrc ! videoconvert ! x264enc ! mp4mux ! filesink location='
        self.orin = orin
        self.raspi = raspi
        self.save_prefix = save_prefix

        # Attach to shared memory
        self.shared_frames = np.ndarray(
            (self.buffer_length, *self.frame_shape),
            dtype=np.uint8,
            buffer=shm_name,
        )

    @staticmethod
    def get_output_filename(folder, suffix='_M', save_prefix=None):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_prefix is None:
            save_prefix = os.uname()[1]
        filename = os.path.join(folder, f"{save_prefix}_{timestamp}{suffix}.mp4")
        return filename

    @staticmethod
    def filename_to_metadata_filepath(filename: Path) -> Path:
        metadata_dir = filename.parent.parent / MOTION_VIDS_METADATA_DIR
        metadata_dir.mkdir(exist_ok=True)
        return metadata_dir / f"{filename.stem}.json"

    def _check_empty(self):
        with self.lock_head, self.lock_tail:
            empty = self.head.value == self.tail.value

        return empty

    def _get_frame(self):
        with self.lock_tail:
            frame_idx = self.tail.value % self.buffer_length
            frame = self.shared_frames[frame_idx]
            self.tail.value = (self.tail.value + 1) % self.buffer_length

        return frame

    def run(self):
        filename = VideoSaver.get_output_filename(self.folder, save_prefix=self.save_prefix)

        logger.info(f"Writing motion video to {filename}")
        if self.orin:
            out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*VIDEO_ENCODER), self.fps, self.resolution)
        else:
            gst_writer = gst_writer_str
            if self.raspi:
                logger.info("Writing with raspi hardware...")
                gst_writer = gst_raspi_writer_str
            out = cv2.VideoWriter(gst_writer + filename, cv2.CAP_GSTREAMER, 0, self.fps, self.resolution)
        
        c = 0
        # Write the pre-motion frames
        while not self._check_empty():
            if c % 20 == 0:
                logger.info(f'Saving pre... {c}')

            frame = self._get_frame()
            out.write(frame)
            c += 1

        c = 0
        # Continue recording until stop_event is set
        while not self.stop_event.is_set():
            with self.condition:
                # Wait for a signal that a new frame is available or stop_event is set
                self.condition.wait_for(lambda: not self._check_empty() or self.stop_event.is_set())

            if not self._check_empty():
                frame = self._get_frame()

            if c % 20 == 0:
                logger.info(f'Saving... {c}')
            out.write(frame)

            c += 1

        out.release()

        metadata = utils.get_video_metadata(filename)
        if metadata is not None:
            logger.info(f"Metadata for video file {filename}: {metadata}")
            metadata_filepath = VideoSaver.filename_to_metadata_filepath(Path(filename))
            logger.info(f"Saving metadata file to harddrive: {str(metadata_filepath)}")
            with open(str(metadata_filepath), 'w') as f:
                json.dump(asdict(metadata), f)
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
        bgsub_max_pixelstability = 7
        threshold_value = 244 # Increase threshold value to minimize noise
        kernel_size = (11, 11) # Increase kernel size to ignore smaller motions
        erode_iter = 1 # Run multiple iterations to incrementally remove smaller objects
        dilate_iter = 1
        min_contour_area = 10000 # Ignore contour objects smaller than this area
        MOTION_EVENTS_THRESH = 0.4 # Ratio of seconds of motion required to trigger detection

        # WARNING: Cannot be larger than 2 or else the program will simply exit when allocating more frames
        BUFFER_LENGTH = 2 # Number of seconds before motion to keep

        MAX_CLIP = 2 * 60 # Maximum number of seconds per clip
        MAX_CONTINUOUS = 30 * 60 # Max continuous video in seconds

        FRAME_RESIZE = (1280, 720)

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
        else:
            fps = int(fps)
            if fps > self.dataloader.fps():
                fps = self.dataloader.fps()

        logger.info(f"FPS: {fps}")

        MAX_FRAMES_CLIP = int(MAX_CLIP * fps)
        MAX_CONTINUOUS_FRAMES = int(MAX_CONTINUOUS * fps)
        MOTION_EVENTS_THRESH_FRAMES = int(MOTION_EVENTS_THRESH * fps)

        if algo == 'MOG2':
            bgsub = cv2.createBackgroundSubtractorMOG2(varThreshold=bgsub_threshold, detectShadows=False)
        else:
            bgsub = cv2.bgsegm.createBackgroundSubtractorCNT(minPixelStability=bgsub_min_pixelstability, useHistory=True, maxPixelStability=bgsub_max_pixelstability, isParallel=True)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, kernel_size)

        warm_up = fps
        buffer_length = int(fps * BUFFER_LENGTH)  # Buffer to save before motion
        motion_detected = False

        # Sacrifice first frame to get frame shape data
        #item = next(self.dataloader.items())
        #frame = item.frame
        #if isinstance(frame, str):
        #    frame = cv2.imread(frame)
        #frame = cv2.resize(frame, FRAME_RESIZE, interpolation=cv2.INTER_AREA)
        frame_shape = (FRAME_RESIZE[1], FRAME_RESIZE[0], 3)

        # Create shared memory between multi processes
        dtype = np.uint8  # Frame data type

        raw = Array('B', int(buffer_length * np.prod(frame_shape) * np.dtype(dtype).itemsize), lock=False)
        shared_frames = np.ndarray(
            (buffer_length, *frame_shape), 
            dtype=dtype, 
            buffer=raw,
        )
        logger.info(f"Size of shared frames: {shared_frames.shape}")

        # Create pointers for circular array
        head = Value('i', 0)
        tail = Value('i', 0)

        # Concurrency-safe constructs
        stop_event = Event()
        lock_head = Lock()
        lock_tail = Lock()
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

            frame = np.ascontiguousarray(item.frame)
            if isinstance(frame, str):
                frame = cv2.imread(frame)
            frame = cv2.resize(frame, FRAME_RESIZE, interpolation=cv2.INTER_AREA)

            if save_video:
                if frame_counter >= MAX_CONTINUOUS_FRAMES:
                    cont_filename = VideoSaver.get_output_filename(cont_dir, '_C', save_prefix=self.save_prefix)
                    logger.info(f"Writing continuous video to {cont_filename}")
                    if orin:
                        cont_vid_out = cv2.VideoWriter(cont_filename, cv2.VideoWriter_fourcc(*VIDEO_ENCODER),
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
                fg_mask = cv2.erode(fg_mask, None, iterations=erode_iter) 
                fg_mask = cv2.dilate(fg_mask, None, iterations=dilate_iter) 

                # Now detect motion
                has_motion = self.detect_motion(fg_mask, min_area=min_contour_area)
            else:
                warm_up -= 1
            if frame_counter % fps == 0:
                end_in_time=time.time()
                elapsed_in_time = (end_in_time - start_in_time) * 1000
                logger.info(f"check motion: {elapsed_in_time:.2f} ms")

            with lock_head:
                frame_idx = head.value % buffer_length
                logger.debug(f"Frame index: {frame_idx}, Head: {head.value}, Buffer length: {buffer_length}")

                with lock_tail:
                    # Check if head is overtaking tail (buffer full)
                    if (head.value + 1) % buffer_length == tail.value:
                        logger.debug("Buffer full! Overwriting old frames.")
                        # Advance the tail to the next frame to make space
                        tail.value = (tail.value + 1) % buffer_length

                shared_frames[frame_idx] = frame
                head.value = (head.value + 1) % buffer_length

            with condition:
                condition.notify() # Signal the VideoSaver thread that a new frame is available

            motion_counter += 1

            # TESTING ONLY
            #if motion_counter >= 100:
            #    has_motion = not has_motion

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
                        video_saver = VideoSaver(
                                shm_name=raw, frame_shape=frame.shape, head=head, tail=tail, 
                                buffer_length=buffer_length, folder=motion_dir, 
                                stop_event=stop_event, lock_head=lock_head, lock_tail=lock_tail, condition=condition, fps=fps, 
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
        except Exception as e:
            logger.error(e)
            pass
        return self.frame_log
