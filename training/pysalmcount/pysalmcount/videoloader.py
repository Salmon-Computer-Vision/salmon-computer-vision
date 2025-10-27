from .dataloader import DataLoader, Item

import cv2
from pathlib import Path
import logging
from threading import Thread
from queue import Queue
import time
import math
import re

logger = logging.getLogger(__name__)

class VideoCaptureError(Exception):
    """Exception raised when video capture fails to open."""
    pass

class VideoLoader(DataLoader):
    def __init__(self, vid_sources, custom_classes=None, gstreamer_on=False, buffer_size=10, target_fps: int=None):
        """
        vid_source: list[string] of anything that can go in VideoCapture() including video paths and RTSP URLs
        """
        self.vid_sources = vid_sources
        self.custom_classes = custom_classes
        self.num_clips = len(vid_sources)
        self.clip_gen = iter(vid_sources)
        self.cur_clip = None
        self.gstreamer_on = gstreamer_on

        buffer_size = buffer_size
        self.frame_buffer = Queue(maxsize=buffer_size)
        self.thread = None
        self.stop_thread = False
        self.target_fps = int(target_fps) if target_fps is not None else target_fps

    def __del__(self):
        self.close()

    def close(self):
        if self.thread and self.thread.is_alive():
            logger.info('Joining frame reader thread...')
            self.stop_thread = True
            self.thread.join()
            logger.info('Grabbing items stopped.')

        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
            logger.info('VideoCapture released.')

    def clips_len(self):
        return self.num_clips

    def next_clip(self):
        if self.thread and self.thread.is_alive():
            # Stop previous thread if it's still running
            self.stop_thread = True
            self.thread.join()

        raw_clip = next(self.clip_gen)
        self.cur_clip = Path(raw_clip)
        logger.info(f"Loading {raw_clip}")
        if self.gstreamer_on:
            logger.info("Loading with gstreamer")
            self.cap = cv2.VideoCapture(str(raw_clip), cv2.CAP_GSTREAMER)
        else:
            logger.info("Loading not gstreamer")
            self.cap = cv2.VideoCapture(str(raw_clip), cv2.CAP_FFMPEG)

        #self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        #self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)

        if not self.cap.isOpened():
            raise VideoCaptureError(f"Error: Could not open video stream {raw_clip}.")

        self.vid_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.vid_fps <= 0 or self.vid_fps > 1000:
            logger.warning(f"Invalid FPS reported ({self.vid_fps}), estimating manually...")
            self.vid_fps = self._estimate_fps(self.cap)

        if self.vid_fps <= 0:
            # Still can't get FPS
            raise VideoCaptureError(f"Error: Cannot determine FPS")
        logger.info(f"Stream or video FPS: {self.vid_fps}")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.is_video = self._detect_source_type(raw_clip)

        # Start a new thread to read frames
        self.stop_thread = False
        self.thread = Thread(target=self._read_frames)
        self.thread.daemon = True
        self.thread.start()

        return self.cur_clip

    def _detect_source_type(self, src):
        try:
            fc = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fc > 0:
                return True  # file
        except Exception:
            pass
        if isinstance(src, str) and re.search(r"\.(mp4|avi|mov|mkv|mpg|mpeg|wmv)$", src, re.I):
            return True
        return False


    def _estimate_fps(self, cap, sample_frames=30, min_duration=0.5):
        """
        Estimate FPS of a stream by timing how long it takes to read a few frames.
        Args:
            cap: An opened cv2.VideoCapture object.
            sample_frames: Number of frames to read for estimating FPS.
            min_duration: Minimum total time in seconds to wait before computing FPS.
        Returns:
            Estimated FPS as float.
        """
        timestamps = []
        for _ in range(sample_frames):
            start = time.time()
            ret, _ = cap.read()
            if not ret:
                break
            timestamps.append(start)
            # Avoid spinning too fast for some broken sources
            if len(timestamps) >= 2 and timestamps[-1] - timestamps[0] >= min_duration:
                break

        if len(timestamps) >= 2:
            duration = timestamps[-1] - timestamps[0]
            return round((len(timestamps) - 1) / duration, 2)
        else:
            return 0.0


    def _read_frames(self):
        """
        Reads frames from the video capture in a separate thread and stores them in a deque.
        """

        keep_all = self.target_fps is None or self.target_fps >= self.vid_fps
        if not math.isfinite(self.vid_fps) or self.vid_fps <= 0:
            keep_all = True # fallback

        step = None
        next_keep = 0.0
        i = 0

        if not keep_all:
            step = float(self.vid_fps) / float(self.target_fps)  # e.g. 30/10 = 3.0
            logger.info(f"Target FPS is lower than video FPS. Will keep every {step} frames")

        count = 0
        start_time = time.monotonic()

        while not self.stop_thread:
            ret, frame = self.cap.read()

            if not ret:
                logger.info('No more frames or failed to retrieve frame, stopping frame reading.')
                self.stop_thread = True
                self.frame_buffer.put(None)  # Sentinel value to signal end of stream
                break

            keep = True
            if not keep_all:
                # keep frames when we cross the next_keep boundary
                keep = (i + 0.000001) >= next_keep
                if keep:
                    next_keep += step
                i += 1

            if keep:
                try:
                    if self.is_video:
                        # For video files: block so you don't drop any frames
                        self.frame_buffer.put(frame, block=True)
                    else:
                        # For live streams: drop if the queue is full
                        self.frame_buffer.put(frame, block=False)
                except queue.Full:
                    if not self.is_video:
                        # only log for streams
                        logger.info("Queue full; dropped frame.")
                    else:
                        raise

            count += 1
            if count % self.vid_fps == 0:
                elapsed_time = (time.monotonic() - start_time) * 1000
                logger.info(f"Retrieval time: {elapsed_time:.2f} ms")
                start_time = time.monotonic()
                count = 0

    def items(self):
        if self.cur_clip is None:
            raise ValueError('Error: No current clip')

        while True:
            frame = self.frame_buffer.get(block=True)
            if frame is None:
                # Sentinel value to stop the consumer
                logger.info('End of video stream detected.')
                break

            yield Item(frame, num_items=self.total_frames)

        self.close()

    def fps(self):
        return self.vid_fps

    def get_frame_num(self):
        return self.cap.get(cv2.CAP_PROP_POS_FRAMES)

    def get_timestamp(self):
        seconds = self.get_frame_num() / self.fps()

        timestamp = f'{int(seconds // 3600):02d}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}'
        return timestamp

    def classes(self) -> dict:
        """
        returns: Returns the custom classes dict. May return None if not initialized.
        """
        return self.custom_classes
