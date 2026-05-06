from .dataloader import DataLoader, Item
from pysalmcount import utils

import cv2
from pathlib import Path
import logging
from threading import Thread
import queue
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
        raw_clip_str = str(raw_clip)
        if raw_clip_str.isdigit():
            logger.info("Loading as directly connected camera")
            self.cap = cv2.VideoCapture(int(raw_clip))
        else:
            if self.gstreamer_on:
                logger.info("Loading with gstreamer")
                self.cap = cv2.VideoCapture(str(raw_clip), cv2.CAP_GSTREAMER)
            else:
                logger.info("Loading with FFMPEG")
                self.cap = cv2.VideoCapture(str(raw_clip), cv2.CAP_FFMPEG)

        #self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        #self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)

        if not self.cap.isOpened():
            raise VideoCaptureError(f"Error: Could not open video stream {raw_clip}.")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.is_video = self._detect_source_type(raw_clip)

        reported_fps = self.cap.get(cv2.CAP_PROP_FPS)

        if self.is_video:
            self.vid_fps = reported_fps

            if self.vid_fps <= 0 or self.vid_fps > 1000:
                logger.warning(
                    f"Invalid FPS reported for video file ({self.vid_fps}), estimating manually..."
                )
                self.vid_fps = self._estimate_fps(self.cap)

                # _estimate_fps() consumes frames, so reset to the beginning for files.
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            if self.vid_fps <= 0:
                raise VideoCaptureError("Error: Cannot determine FPS for video file")

        else:
            # RTSP/live stream:
            # Do not estimate FPS by timing cap.read(); that measures buffer/decode speed,
            # not the true camera FPS.
            if reported_fps > 0 and reported_fps <= 120:
                self.vid_fps = reported_fps
                logger.info(f"Using reported live stream FPS: {self.vid_fps}")
            else:
                fallback_fps = self.target_fps if self.target_fps is not None else 10
                logger.warning(
                    f"Invalid FPS reported for live stream ({reported_fps}); "
                    f"using fallback FPS={fallback_fps}. "
                    "Live stream frame sampling will use wall-clock time."
                )
                self.vid_fps = fallback_fps

        logger.info(f"Stream or video FPS: {self.vid_fps}")

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
    

    def _put_live_frame_latest(self, frame):
        """
        Put a frame into the live-stream queue.

        If the queue is full, drop the oldest queued frame and insert the newest
        frame. This keeps latency low for RTSP/live sources.
        """
        try:
            self.frame_buffer.put(frame, block=False)
            return True
        except queue.Full:
            pass

        # Queue is full. Drop the oldest frame, then try to enqueue the newest one.
        try:
            _ = self.frame_buffer.get_nowait()
        except queue.Empty:
            pass

        try:
            self.frame_buffer.put(frame, block=False)
            logger.info("Queue full; dropped oldest frame and kept newest frame.")
            return True
        except queue.Full:
            logger.info("Queue still full after dropping oldest frame; dropped newest frame.")
            return False


    def _read_frames(self):
        """
        Reads frames from the video capture in a separate thread.

        Behavior:
        - Video files: use source FPS and frame-ratio downsampling.
        - Live streams/RTSP: use wall-clock throttling based on target_fps.
          This avoids estimating FPS from cap.read() speed, which can be wrong
          when FFmpeg/OpenCV drains buffered frames quickly.
        """

        is_live_stream = not self.is_video

        # -----------------------------
        # Video-file downsampling setup
        # -----------------------------
        keep_all_file_frames = True
        ratio = 1.0
        accum = 0.0

        if self.is_video:
            keep_all_file_frames = (
                self.target_fps is None
                or not math.isfinite(self.vid_fps)
                or self.vid_fps <= 0
                or self.target_fps >= self.vid_fps
            )

            if not keep_all_file_frames:
                ratio = self.target_fps / self.vid_fps
                logger.info(
                    f"Video file source FPS is {self.vid_fps:.2f}; "
                    f"target FPS is {self.target_fps}. "
                    f"Will keep {ratio:.3f} of decoded frames."
                )

        # -----------------------------
        # Live-stream wall-clock setup
        # -----------------------------
        if is_live_stream and self.target_fps is not None and self.target_fps > 0:
            emit_interval = 1.0 / float(self.target_fps)
            next_emit_time = time.monotonic()
            logger.info(
                f"Live stream detected. Will sample by wall clock at "
                f"{self.target_fps} FPS, interval={emit_interval:.3f}s."
            )
        else:
            emit_interval = None
            next_emit_time = None
            if is_live_stream:
                logger.info("Live stream detected. No target_fps set; keeping all received frames.")

        # -----------------------------
        # Health-check logging setup
        # -----------------------------
        kept_count = 0
        read_count = 0
        dropped_by_sampler = 0
        last_health_log_time = time.monotonic()
        health_log_interval = 30.0  # seconds; avoids relying on bogus RTSP FPS

        while not self.stop_thread:
            ret, frame = self.cap.read()
            read_count += 1

            if not ret:
                logger.info("No more frames or failed to retrieve frame, stopping frame reading.")
                self.stop_thread = True

                # Avoid blocking forever if the queue is full.
                try:
                    self.frame_buffer.put(None, block=False)
                except queue.Full:
                    if is_live_stream:
                        try:
                            _ = self.frame_buffer.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self.frame_buffer.put(None, block=False)
                        except queue.Full:
                            pass
                    else:
                        self.frame_buffer.put(None, block=True)

                break

            keep = True

            if self.is_video:
                # For files, downsample based on source FPS.
                if not keep_all_file_frames:
                    accum += ratio
                    if accum >= 1.0:
                        accum -= 1.0
                        keep = True
                    else:
                        keep = False

            else:
                # For RTSP/live streams, downsample by wall-clock time.
                if emit_interval is not None:
                    now = time.monotonic()

                    if now >= next_emit_time:
                        keep = True

                        # Schedule the next emitted frame based on the intended cadence.
                        # This avoids drift when reads are stable.
                        next_emit_time += emit_interval

                        # If the reader was blocked/stalled and fell far behind,
                        # resync instead of trying to "catch up" by emitting bursts.
                        if next_emit_time < now - emit_interval:
                            next_emit_time = now + emit_interval
                    else:
                        keep = False

            if not keep:
                dropped_by_sampler += 1
                continue

            if self.is_video:
                # For files, block so no selected frames are dropped.
                self.frame_buffer.put(frame, block=True)
                kept_count += 1
            else:
                # For live streams, keep newest frames and avoid stale backlog.
                if self._put_live_frame_latest(frame):
                    kept_count += 1

            # Health logging based on real elapsed time, not self.vid_fps.
            now = time.monotonic()
            if now - last_health_log_time >= health_log_interval:
                elapsed = now - last_health_log_time
                read_fps = read_count / elapsed if elapsed > 0 else 0.0
                kept_fps = kept_count / elapsed if elapsed > 0 else 0.0

                logger.info(
                    f"Frame reader stats: read_fps={read_fps:.2f}, "
                    f"kept_fps={kept_fps:.2f}, "
                    f"read_count={read_count}, kept_count={kept_count}, "
                    f"dropped_by_sampler={dropped_by_sampler}, "
                    f"queue_size={self.frame_buffer.qsize()}"
                )

                read_count = 0
                kept_count = 0
                dropped_by_sampler = 0
                last_health_log_time = now

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

    def is_video(self):
        return self.is_video

    def classes(self) -> dict:
        """
        returns: Returns the custom classes dict. May return None if not initialized.
        """
        return self.custom_classes
