from .dataloader import DataLoader, Item

import cv2
from pathlib import Path
import logging
from threading import Thread
from queue import Queue
import time
import math

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
        if self.thread and self.thread.is_alive():
            self.stop_thread = True
            self.thread.join()
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

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
        logger.info(f"Stream or video FPS: {self.vid_fps}")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Start a new thread to read frames
        self.stop_thread = False
        self.thread = Thread(target=self._read_frames)
        self.thread.daemon = True
        self.thread.start()

        return self.cur_clip

    def _read_frames(self):
        """
        Reads frames from the video capture in a separate thread and stores them in a deque.
        """

        prev_time = 0
        count = 0
        overflow_elapsed = 0
        skip_frame_target = None
        if self.target_fps is not None and self.target_fps < self.vid_fps:
            skip_frame_target = self.vid_fps / (self.vid_fps - self.target_fps)
            cur_frame_target = math.trunc(skip_frame_target)
            remainder_frame = skip_frame_target % 1
        #target_time_elapse = 1. / self.target_fps
        while not self.stop_thread:
            if count % self.vid_fps == 0:
                start_time=time.time()

            #if self.target_fps is not None and self.target_fps < self.vid_fps:
            #    time_elapsed = time.time() - prev_time + overflow_elapsed

            ret, frame = self.cap.read()
            if ret:
                if self.target_fps is not None:
                    #if self.target_fps < self.vid_fps and time_elapsed < target_time_elapse:
                    #    continue
                    #else:
                    #    overflow_elapsed = time_elapsed - target_time_elapse
                    #    prev_time = time.time()
                    if skip_frame_target is not None and count >= cur_frame_target:
                        cur_frame_target = skip_frame_target + remainder_frame
                        remainder_frame = cur_frame_target % 1
                        cur_frame_target = math.trunc(cur_frame_target)
                        count = 0
                        continue
                self.frame_buffer.put(frame, block=True)

                if count % self.vid_fps == 0:
                    end_time=time.time()
                    elapsed_time = (end_time - start_time) * 1000
                    logger.info(f"Retrieval time: {elapsed_time:.2f} ms")
                    if skip_frame_target is None:
                        count = 0
                count += 1
            else:
                logger.info('No more frames or failed to retrieve frame, stopping frame reading.')
                self.stop_thread = True
                self.frame_buffer.put(None)  # Sentinel value to signal end of stream
                break

    def items(self):
        if self.cur_clip is None:
            raise ValueError('Error: No current clip')

        while not self.stop_thread:
            frame = self.frame_buffer.get(block=True)
            if frame is None:
                # Sentinel value to stop the consumer
                logger.info('End of video stream detected.')
                break

            yield Item(frame, num_items=self.total_frames)

        # ✅ Ensure the reader thread is joined
        if self.thread and self.thread.is_alive():
            logger.info('Joining frame reader thread...')
            self.thread.join()
            logger.info('Grabbing items stopped.')

        if self.cap.isOpened():
            self.cap.release()
            logger.info('VideoCapture released.')

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
