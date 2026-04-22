#!/usr/bin/env python3
from .dataloader import DataLoader
from pysalmcount import utils

import cv2
import numpy as np
from collections import deque
import argparse
import datetime
import os
import errno
import secrets
import threading
#from threading import Thread, Event, Lock, Condition
from multiprocessing import shared_memory, Process, Event, Lock, Condition, Value, Array
import logging
import time
from enum import Enum
from pathlib import Path
import json
from dataclasses import asdict, dataclass
import re
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

gst_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert ! video/x-raw,format=BGRx ! nvvidconv ! nvv4l2h264enc vbv-size=200000 bitrate=3000000 insert-vui=1 ! h264parse ! mp4mux ! filesink location="
gst_raspi_writer_str = "appsrc ! video/x-raw,format=BGR ! queue ! videoconvert !  v4l2h264enc extra-controls=encode,video_bitrate=3000000 ! h264parse ! qtmux ! filesink location="
MOTION_VIDS = 'motion_vids'
MOTION_VIDS_STAGING = 'motion_vids_staging'
MOTION_VIDS_METADATA_DIR = 'motion_vids_metadata'
VIDEO_ENCODER = 'avc1'

# Clip timing. Single source of truth: changing these values updates BOTH the
# single-camera state machine (MotionDetector.run) AND the multi-camera
# coordinator (MotionEventCoordinator defaults).
MAX_CLIP_SECONDS = 120.0  # Hard cap on a single motion clip.
PRE_ROLL_SECONDS = 2.0    # Ring-buffer depth (also the pre-roll of every clip).
# WARNING (pre-existing): raising PRE_ROLL_SECONDS above 2.0 triggers the
# shared-memory allocation issue the original inline comment warned about.
# A runtime check in MotionDetector.run enforces <= 2.0 until root-caused.
POST_ROLL_SECONDS = 5.0   # Seconds of no motion before a clip closes.


class TickAction(Enum):
    CONTINUE = 1   # no clip-state change
    ROLLOVER = 2   # stop current clip (final=False); on next iter, spawn next part
    FINALIZE = 3   # stop current clip (final=True); leave event


@dataclass(frozen=True)
class ClipInfo:
    """Per-clip information minted by MotionEventCoordinator and passed into
    VideoSaver. All clips of one logical motion episode share event_id and
    event_start_ts; part_number distinguishes rolled segments within a cam."""
    event_id: str
    event_start_ts: datetime.datetime
    part_number: int
    originator: str


class MotionEventCoordinator:
    """Shared timing + fan-out across N cameras (N >= 2).

    Drives lock-step clip boundaries so every cam produces the same number of
    clips with the same wall-clock length (to within one frame period).

    Lifecycle:
      idle -> enter_event(any cam) -> open (event_id/event_start_ts minted,
      fan-out flags set for other cams) -> other cams join via take_trigger +
      enter_event -> MAX_CLIP rollovers broadcast via _rollover_pending ->
      final stop broadcast via _finalize_pending once last_motion_wall is
      stale for POST_ROLL_SECONDS -> every cam calls leave_event -> idle.
    """

    def __init__(self, cam_names: List[str],
                 max_clip_seconds: float = MAX_CLIP_SECONDS,
                 post_roll_seconds: float = POST_ROLL_SECONDS):
        if len(cam_names) < 2:
            raise ValueError(
                "MotionEventCoordinator requires N >= 2 cameras, got "
                f"{len(cam_names)}"
            )
        if len(set(cam_names)) != len(cam_names):
            raise ValueError(
                f"Duplicate cam_names not allowed: {cam_names}"
            )
        self._lock = threading.Lock()
        self._cam_names: List[str] = list(cam_names)
        # Fan-out "start recording now" flags set at event open. Consumed by
        # other cams in take_trigger().
        self._triggers: Dict[str, threading.Event] = {
            n: threading.Event() for n in cam_names
        }
        # Per-cam rollover/finalize pending bits broadcast by tick().
        self._rollover_pending: Dict[str, bool] = {n: False for n in cam_names}
        self._finalize_pending: Dict[str, bool] = {n: False for n in cam_names}
        # Active-event state.
        self._active_event_id: Optional[str] = None
        self._active_event_start: Optional[datetime.datetime] = None
        self._event_originator: Optional[str] = None
        self._current_part_number: int = 0
        # time.monotonic() timestamps for drift-free shared timing.
        self._current_part_start_wall: Optional[float] = None
        self._last_motion_wall: Optional[float] = None
        self._cams_recording: Set[str] = set()
        self._max_clip_seconds = float(max_clip_seconds)
        self._post_roll_seconds = float(post_roll_seconds)

    @staticmethod
    def _mint_event_id(now_utc: datetime.datetime) -> str:
        return f"{now_utc.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(3)}"

    @staticmethod
    def event_id_short(event_id: str) -> str:
        """Return the short (6-hex) suffix used in filenames."""
        # Format is 'YYYYMMDDTHHMMSSZ_abcdef'; after the underscore is the hex.
        return event_id.rsplit('_', 1)[-1]

    def enter_event(self, cam_name: str) -> ClipInfo:
        """Atomic mint-or-join.

        - Idle: mint (event_id, event_start_ts), record originator=cam,
          set part_number=1, set current_part_start_wall and last_motion_wall
          to now, set fan-out flags for every OTHER cam.
        - Active: return current clip info unchanged.

        In both cases: add cam_name to _cams_recording and clear this cam's
        own fan-out flag (defense against the race where A mints and B opens
        locally in the same instant -- B's fan-out flag would otherwise
        linger as stale state until event close).
        """
        if cam_name not in self._triggers:
            raise ValueError(f"Unknown cam_name: {cam_name!r}")
        with self._lock:
            if self._active_event_id is None:
                # Mint.
                now_wall = time.monotonic()
                now_utc = datetime.datetime.utcnow()
                assert cam_name not in self._cams_recording, (
                    f"enter_event mint called but {cam_name} is already "
                    f"recording (coordinator state corrupted?)"
                )
                self._active_event_id = self._mint_event_id(now_utc)
                self._active_event_start = now_utc
                self._event_originator = cam_name
                self._current_part_number = 1
                self._current_part_start_wall = now_wall
                self._last_motion_wall = now_wall
                # Fan out to every other cam. Clear this cam's own flag below.
                for other in self._cam_names:
                    if other != cam_name:
                        self._triggers[other].set()
            # Always join (mint branch also joins as originator).
            self._cams_recording.add(cam_name)
            self._triggers[cam_name].clear()
            return ClipInfo(
                event_id=self._active_event_id,
                event_start_ts=self._active_event_start,
                part_number=self._current_part_number,
                originator=self._event_originator,
            )

    def get_current_clip_info(self) -> ClipInfo:
        """Read-only snapshot of current clip info. Used by the rollover-
        restart path (iter N+1 after a ROLLOVER) and any diagnostic path.
        Raises RuntimeError if no event is active."""
        with self._lock:
            if self._active_event_id is None:
                raise RuntimeError(
                    "get_current_clip_info called while coordinator is idle"
                )
            return ClipInfo(
                event_id=self._active_event_id,
                event_start_ts=self._active_event_start,
                part_number=self._current_part_number,
                originator=self._event_originator,
            )

    def take_trigger(self, cam_name: str) -> bool:
        """Atomic consume of fan-out flag. Called once per frame by each cam
        while motion_detected=False. Returns True exactly once per set."""
        ev = self._triggers.get(cam_name)
        if ev is None:
            return False
        # threading.Event's is_set + clear is not atomic on its own, but
        # setting is idempotent and we're the sole consumer for this cam, so
        # acquiring the coordinator lock around it keeps enter_event and
        # take_trigger race-free against each other.
        with self._lock:
            if ev.is_set():
                ev.clear()
                return True
            return False

    def tick(self, cam_name: str, has_motion: bool) -> TickAction:
        """Called once per frame by each cam while motion_detected=True.

        Finalize wins over rollover when both conditions would fire in the
        same tick (avoids a trailing near-empty next-part clip).
        """
        with self._lock:
            # 1. Pending signals from earlier ticks win first. Finalize is
            # checked before rollover to match overall precedence.
            if self._finalize_pending.get(cam_name):
                self._finalize_pending[cam_name] = False
                return TickAction.FINALIZE
            if self._rollover_pending.get(cam_name):
                self._rollover_pending[cam_name] = False
                return TickAction.ROLLOVER

            if self._active_event_id is None:
                # No active event; nothing to do (shouldn't normally happen
                # because caller should only tick while motion_detected=True).
                return TickAction.CONTINUE

            now_wall = time.monotonic()
            if has_motion:
                self._last_motion_wall = now_wall

            # 2. Finalize condition: no cam has reported motion for
            # post_roll_seconds.
            if (self._last_motion_wall is not None and
                    now_wall - self._last_motion_wall >= self._post_roll_seconds):
                for n in self._cam_names:
                    self._finalize_pending[n] = True
                    # Finalize wins over any stale rollover that hasn't been
                    # consumed yet (prevents trailing empty next-part clips).
                    self._rollover_pending[n] = False
                # Consume this cam's bit immediately.
                self._finalize_pending[cam_name] = False
                return TickAction.FINALIZE

            # 3. Rollover condition: this clip has run for max_clip_seconds.
            if (self._current_part_start_wall is not None and
                    now_wall - self._current_part_start_wall >= self._max_clip_seconds):
                self._current_part_number += 1
                self._current_part_start_wall = now_wall
                for n in self._cam_names:
                    self._rollover_pending[n] = True
                # Consume this cam's bit immediately.
                self._rollover_pending[cam_name] = False
                return TickAction.ROLLOVER

            return TickAction.CONTINUE

    def consume_finalize_if_pending(self, cam_name: str) -> bool:
        """Check-and-clear this cam's finalize-pending bit.

        Used by MotionDetector at the top of the rollover-restart path: if
        finalize was broadcast in the gap between the rollover iter and the
        restart iter, we want to short-circuit to FINALIZE and skip spawning
        a next-part VideoSaver that would immediately be killed.
        """
        with self._lock:
            if self._finalize_pending.get(cam_name):
                self._finalize_pending[cam_name] = False
                return True
            return False

    def leave_event(self, cam_name: str) -> None:
        """Idempotent. Remove cam from _cams_recording. When the set is
        empty, close the event: clear event_id/start/originator/part, clear
        all _triggers/_rollover_pending/_finalize_pending flags."""
        with self._lock:
            self._cams_recording.discard(cam_name)
            if not self._cams_recording and self._active_event_id is not None:
                self._active_event_id = None
                self._active_event_start = None
                self._event_originator = None
                self._current_part_number = 0
                self._current_part_start_wall = None
                self._last_motion_wall = None
                for n in self._cam_names:
                    self._triggers[n].clear()
                    self._rollover_pending[n] = False
                    self._finalize_pending[n] = False

    def is_event_active(self) -> bool:
        with self._lock:
            return self._active_event_id is not None

class VideoSaver(Process):
    def __init__(self, shm_name, frame_shape, head: Value, tail: Value, buffer_length, folder, stop_event, lock_head, lock_tail, condition, fps=10.0,
            orin=False, raspi=False, save_prefix=None, is_video=False, filename=None, frame_count=0,
            event_id: Optional[str] = None,
            event_start_ts: Optional[datetime.datetime] = None,
            part_number: Optional[int] = None,
            cam_name: Optional[str] = None,
            triggered_by: Optional[str] = None):
        super().__init__()
        self.frame_shape = frame_shape
        self.head = head
        self.tail = tail
        self.buffer_length = buffer_length
        self.folder = Path(folder)
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
        self.is_video = is_video
        self.filename = filename
        self.frame_count = frame_count
        # Multi-camera event fields. All None in single-cam mode.
        self.event_id = event_id
        self.event_start_ts = event_start_ts
        self.part_number = part_number
        self.cam_name = cam_name
        self.triggered_by = triggered_by

        if is_video and filename is None:
            logger.warn("Filename is empty. Will fallback on timestampped name")

        # Attach to shared memory
        self.shared_frames = np.ndarray(
            (self.buffer_length, *self.frame_shape),
            dtype=np.uint8,
            buffer=shm_name,
        )

    def _get_md_filename(self, suffix='_M', save_prefix=None):
        # Multi-camera: use shared event timestamp + event hash + part number
        # so every clip of one episode groups together and per-cam rolled
        # segments stay ordered. `save_prefix` already carries the cam name.
        if self.event_id is not None and self.event_start_ts is not None:
            ts = self.event_start_ts.strftime("%Y%m%d_%H%M%S")
            short = MotionEventCoordinator.event_id_short(self.event_id)
            part = self.part_number if self.part_number is not None else 1
            prefix = save_prefix if save_prefix is not None else os.uname()[1]
            filename = self.folder / (
                f"{prefix}_{ts}_E{short}_p{part:03d}{suffix}.mp4"
            )
            return str(filename)

        if not self.is_video or self.filename is None:
            filename = VideoSaver.get_output_filename(self.folder, save_prefix=self.save_prefix)
        else:
            new_timestr = self.filename
            # Extract timestamp
            match = re.search(r'(\d{8}_\d{6})', self.filename)
            if match:
                timestr = match.group(1)
                base_time = datetime.datetime.strptime(timestr, "%Y%m%d_%H%M%S")

                # compute elapsed time
                elapsed_seconds = self.frame_count / self.fps
                logger.info(f"Frame count: {self.frame_count}, FPS: {self.fps}, Elapsed seconds before clip: {elapsed_seconds}")
                new_time = base_time + datetime.timedelta(seconds=elapsed_seconds)

                # reformat for filename
                new_timestr = new_time.strftime("%Y%m%d_%H%M%S")

            filename = self.folder / f"{save_prefix}_{new_timestr}{suffix}.mp4"

        return str(filename)

    @staticmethod
    def get_output_filename(folder: str, suffix='_M', save_prefix=None):
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

        with self.condition:
            self.condition.notify() # Signal to Producer to stop blocking

        return frame

    def run(self):
        filename = self._get_md_filename(save_prefix=self.save_prefix)

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

        with self.condition:
            self.condition.notify_all() # Signal to Producer to stop blocking

        metadata = utils.get_video_metadata(filename)
        if metadata is None:
            logger.error(f"Could not generate metadata for file: {filename}")

        # Build the metadata JSON payload.
        # - Single-cam (event_id is None): preserve today's behavior, only
        #   write the file when ffmpeg metadata probe succeeded.
        # - Multi-cam (event_id set): always write the file, even if the
        #   probe failed, so downstream grouping by event_id always works.
        payload = asdict(metadata) if metadata is not None else {}
        if self.event_id is not None:
            payload.update({
                "event_id": self.event_id,
                "event_start_ts": (
                    self.event_start_ts.isoformat()
                    if self.event_start_ts is not None else None
                ),
                "cam_name": self.cam_name,
                "triggered_by": self.triggered_by,
                "part_number": self.part_number,
            })

        if payload:
            metadata_filepath = VideoSaver.filename_to_metadata_filepath(Path(filename))
            logger.info(f"Saving metadata file to harddrive: {str(metadata_filepath)}")
            with open(str(metadata_filepath), 'w') as f:
                json.dump(payload, f)

class _CamLoggerAdapter(logging.LoggerAdapter):
    """Prefix every log record with [cam_name] regardless of the root
    formatter, so a combined multi-cam log file stays readable."""

    def __init__(self, base_logger: logging.Logger, cam_name: str):
        super().__init__(base_logger, {"cam_name": cam_name})
        self._cam_name = cam_name

    def process(self, msg, kwargs):
        return f"[{self._cam_name}] {msg}", kwargs


class MotionDetector:
    FILENAME = 'filename'
    CLIPS = 'clips'

    def __init__(self, dataloader: DataLoader, save_folder, save_video=True, save_cont_video=True, is_video=False, save_prefix=None, ping_url='https://google.com',
                 coordinator: Optional[MotionEventCoordinator] = None,
                 cam_name: Optional[str] = None):
        self.dataloader = dataloader
        self.save_folder = save_folder
        self.frame_log = {}
        self.save_prefix = save_prefix
        self.ping_url = ping_url

        self.is_video = is_video
        self.save_video = save_video
        self.save_cont_video = save_cont_video
        self.motion_counter = 0
        self.motion_detected = False

        # Multi-camera coordination. coordinator is None => single-cam mode
        # with exact legacy behavior.
        self.coordinator = coordinator
        self.cam_name = cam_name
        self._awaiting_next_part: bool = False
        # Per-cam log adapter so every record is tagged with [cam_name] in
        # multi-cam mode. In single-cam mode fall back to the module logger.
        if cam_name is not None:
            self.log = _CamLoggerAdapter(logger, cam_name)
        else:
            self.log = logger

        # Concurrency-safe constructs
        self.stop_event = Event()
        self.lock_head = Lock()
        self.lock_tail = Lock()
        self.condition = Condition()


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

    def stop_video_saving(self, final: bool = True):
        """Stop the currently-recording VideoSaver.

        final=True  -> post-roll or end-of-stream; in multi-cam mode also
                       calls coordinator.leave_event so the cam drops out of
                       _cams_recording (possibly closing the event).
        final=False -> MAX_CLIP rollover; the cam will start its next part
                       on the next loop iteration via the _awaiting_next_part
                       path; coordinator participation is preserved.
        """
        self.motion_counter = 0
        if self.save_video and not self.stop_event.is_set():
            if final:
                self.log.info("Stopping recording.")
            else:
                self.log.info("Rolling to next clip part.")
            self.stop_event.set()
            with self.condition:
                self.condition.notify_all()  # Signal the VideoSaver thread to stop waiting and finish
            self.motion_detected = False
        elif not self.save_video:
            self.motion_detected = False

        if final and self.coordinator is not None and self.cam_name is not None:
            try:
                self.coordinator.leave_event(self.cam_name)
            except Exception:
                # leave_event is idempotent and must never raise; log and swallow
                # to keep shutdown paths robust.
                self.log.exception("coordinator.leave_event raised")


    def _spawn_video_saver(self, motion_dir, raw, frame_shape, head, tail,
                           buffer_length, fps, orin, raspi, cur_clip_name,
                           frame_counter, clip_info: Optional[ClipInfo]):
        """Construct and start a new VideoSaver for this cam's next clip.

        Shared by all three multi-cam entry points (fan-out, local-open,
        rollover-restart) as well as the single-cam open path. When
        ``clip_info`` is None we're in single-cam mode and VideoSaver falls
        back to today's timestamp-based filename.
        """
        self.stop_event.clear()
        vs_kwargs = {}
        if clip_info is not None:
            vs_kwargs.update(
                event_id=clip_info.event_id,
                event_start_ts=clip_info.event_start_ts,
                part_number=clip_info.part_number,
                cam_name=self.cam_name,
                triggered_by=clip_info.originator,
            )
        video_saver = VideoSaver(
            shm_name=raw, frame_shape=frame_shape, head=head, tail=tail,
            buffer_length=buffer_length, folder=motion_dir,
            stop_event=self.stop_event, lock_head=self.lock_head,
            lock_tail=self.lock_tail, condition=self.condition, fps=fps,
            orin=orin, raspi=raspi, save_prefix=self.save_prefix,
            is_video=self.is_video, filename=cur_clip_name,
            frame_count=frame_counter, **vs_kwargs,
        )
        video_saver.start()
        self.motion_detected = True
        self.motion_counter = 0
        return video_saver

    def run(self, algo='MOG2', fps: int=None, orin=False, raspi=False, staging=False):
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

        # Clip-timing values come from the module-level single source of truth.
        # Change MAX_CLIP_SECONDS / PRE_ROLL_SECONDS / POST_ROLL_SECONDS at the
        # top of this file and both single-cam and multi-cam pick up the new
        # values (the coordinator defaults read from the same constants).
        if PRE_ROLL_SECONDS > 2.0:
            raise ValueError(
                f"PRE_ROLL_SECONDS={PRE_ROLL_SECONDS} > 2.0 is known to crash "
                "the shared-memory allocation on this code path; see TODO at "
                "the top of motion_detect_stream.py."
            )
        BUFFER_LENGTH = PRE_ROLL_SECONDS  # seconds
        MAX_CLIP = MAX_CLIP_SECONDS       # seconds
        MAX_CONTINUOUS = 30 * 60          # seconds; unrelated to motion clips

        FRAME_RESIZE = (1280, 720)

        # Race-safe directory creation for multi-cam threads sharing one
        # device_id folder. os.mkdir's no-exist check was not thread-safe.
        cont_dir = os.path.join(self.save_folder, 'cont_vids')
        Path(cont_dir).mkdir(parents=True, exist_ok=True)

        if staging:
            motion_dir = os.path.join(self.save_folder, MOTION_VIDS_STAGING)
        else:
            motion_dir = os.path.join(self.save_folder, MOTION_VIDS)
        Path(motion_dir).mkdir(parents=True, exist_ok=True)

        cur_clip = self.dataloader.next_clip()
        self.frame_log[cur_clip.name] = []

        if fps is None:
            # Retrieve the FPS of the video stream
            fps = self.dataloader.fps()
        else:
            if fps > self.dataloader.fps():
                fps = self.dataloader.fps()

        self.log.info(f"FPS: {fps}")

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
        self.motion_detected = False
        self._awaiting_next_part = False

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
        self.log.info(f"Size of shared frames: {shared_frames.shape}")

        # Create pointers for circular array
        head = Value('i', 0)
        tail = Value('i', 0)

        delay = int(fps * POST_ROLL_SECONDS) # Number of frames of no-motion before stopping (single-cam only)
        count_delay = 0

        video_saver = None
        frame_counter = MAX_CONTINUOUS_FRAMES if self.save_cont_video else 0
        vid_counter = 0
        self.motion_counter = 0
        num_motion_events = 0
        frame_start = 0

        multicam = self.coordinator is not None and self.cam_name is not None

        try:
            for item in self.dataloader.items():
                if utils.is_check_time(frame_counter, fps):
                    start_time=time.time()

                frame = np.ascontiguousarray(item.frame)
                if isinstance(frame, str):
                    frame = cv2.imread(frame)
                frame = cv2.resize(frame, FRAME_RESIZE, interpolation=cv2.INTER_AREA)

                if self.save_cont_video:
                    if frame_counter >= MAX_CONTINUOUS_FRAMES:
                        cont_filename = VideoSaver.get_output_filename(cont_dir, '_C', save_prefix=self.save_prefix)
                        self.log.info(f"Writing continuous video to {cont_filename}")
                        if orin:
                            cont_vid_out = cv2.VideoWriter(cont_filename, cv2.VideoWriter_fourcc(*VIDEO_ENCODER),
                                    fps, (frame.shape[1], frame.shape[0]))
                        else:
                            gst_writer = gst_writer_str
                            if raspi:
                                self.log.info("Writing with raspi hardware...")
                                gst_writer = gst_raspi_writer_str
                            cont_vid_out = cv2.VideoWriter(gst_writer + cont_filename,
                                                           cv2.CAP_GSTREAMER, 0, fps, (frame.shape[1], frame.shape[0]))
                            self.log.info(f"Created VideoWriter to {cont_filename}")
                        frame_counter = 0

                    if utils.is_check_time(frame_counter, fps):
                        start_in_time = time.time()

                    cont_vid_out.write(frame)

                    if utils.is_check_time(frame_counter, fps):
                        end_in_time=time.time()
                        elapsed_in_time = (end_in_time - start_in_time) * 1000
                        self.log.info(f"Cont save: {elapsed_in_time:.2f} ms")

                if utils.is_check_time(frame_counter, fps):
                    start_in_time = time.time()

                # Apply background subtraction algorithm to get the foreground mask
                fg_mask = bgsub.apply(frame)

                if utils.is_check_time(frame_counter, fps):
                    end_in_time=time.time()
                    elapsed_in_time = (end_in_time - start_in_time) * 1000
                    self.log.info(f"BGSub: {elapsed_in_time:.2f} ms")
                #cont_vid_out.write(cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2RGB))

                if utils.is_check_time(frame_counter, fps):
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
                if utils.is_check_time(frame_counter, fps):
                    end_in_time=time.time()
                    elapsed_in_time = (end_in_time - start_in_time) * 1000
                    self.log.info(f"check motion: {elapsed_in_time:.2f} ms")

                with self.lock_head:
                    frame_idx = head.value % buffer_length
                    self.log.debug(f"Frame index: {frame_idx}, Head: {head.value}, Buffer length: {buffer_length}")

                    with self.lock_tail:
                        buf_full = (head.value + 1) % buffer_length == tail.value

                # Check if head is overtaking tail (buffer full)
                if buf_full and self.motion_detected:
                    # Wait until saver consumes a frame
                    with self.condition:
                        self.condition.wait_for(
                            lambda: (head.value + 1) % buffer_length != tail.value or self.stop_event.is_set()
                        )
                elif buf_full:
                    self.log.debug("Buffer full! Overwriting old frames.")
                    with self.lock_tail:
                        # Advance the tail to the next frame to make space
                        tail.value = (tail.value + 1) % buffer_length

                with self.lock_head:
                    shared_frames[frame_idx] = frame
                    head.value = (head.value + 1) % buffer_length

                with self.condition:
                    self.condition.notify() # Signal the VideoSaver thread that a new frame is available

                if self.motion_detected:
                    self.motion_counter += 1

                # ----- State machine -----
                if multicam:
                    # --- Multi-cam path ---
                    if self._awaiting_next_part:
                        # Previous iteration returned ROLLOVER; spawn the next
                        # part's VideoSaver on THIS iteration. First short-
                        # circuit to FINALIZE if the finalize condition fired
                        # in the gap -- prevents a 1-2 frame trailing clip.
                        if self.coordinator.consume_finalize_if_pending(self.cam_name):
                            self._awaiting_next_part = False
                            # Nothing to stop (old saver already closed via
                            # rollover); just leave the event and reset state.
                            self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                            if self.coordinator is not None:
                                try:
                                    self.coordinator.leave_event(self.cam_name)
                                except Exception:
                                    self.log.exception("coordinator.leave_event raised")
                            self.motion_detected = False
                            num_motion_events = 0
                            count_delay = 0
                        else:
                            info = self.coordinator.get_current_clip_info()
                            self.log.info(
                                f"Rolling into part {info.part_number} of event {info.event_id}"
                            )
                            if self.save_video:
                                video_saver = self._spawn_video_saver(
                                    motion_dir, raw, frame.shape, head, tail,
                                    buffer_length, fps, orin, raspi,
                                    cur_clip.name, frame_counter, info,
                                )
                            else:
                                self.motion_detected = True
                                self.motion_counter = 0
                            self._awaiting_next_part = False
                    elif self.motion_detected:
                        action = self.coordinator.tick(self.cam_name, has_motion)
                        if action is TickAction.ROLLOVER:
                            self.log.info("Max clip length reached; rollover")
                            self.stop_video_saving(final=False)
                            self._awaiting_next_part = True
                        elif action is TickAction.FINALIZE:
                            self.log.info("Post-roll exceeded; finalizing clip")
                            self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                            self.stop_video_saving(final=True)
                            # Reset noise-filter state so the next event
                            # still requires 0.4 s of sustained motion.
                            num_motion_events = 0
                            count_delay = 0
                        # action CONTINUE: nothing extra; frame already in buf
                    else:
                        # Idle in multi-cam mode.
                        if self.coordinator.take_trigger(self.cam_name):
                            # Fan-out: another cam opened an event.
                            info = self.coordinator.enter_event(self.cam_name)
                            self.log.info(
                                f"Fan-out trigger; joining event {info.event_id} "
                                f"(originator={info.originator}) as part "
                                f"{info.part_number}"
                            )
                            frame_start = frame_counter
                            if self.save_video:
                                video_saver = self._spawn_video_saver(
                                    motion_dir, raw, frame.shape, head, tail,
                                    buffer_length, fps, orin, raspi,
                                    cur_clip.name, frame_counter, info,
                                )
                            else:
                                self.motion_detected = True
                                self.motion_counter = 0
                            num_motion_events = 0
                            count_delay = 0
                        else:
                            # Local-motion detection path (threshold-gated).
                            # Only the bookkeeping matters while idle -- we
                            # don't need the inner stop branches (can't fire
                            # because motion_detected is False here).
                            if has_motion:
                                num_motion_events += 1
                                count_delay = 0
                                if num_motion_events >= MOTION_EVENTS_THRESH_FRAMES:
                                    info = self.coordinator.enter_event(self.cam_name)
                                    self.log.info(
                                        f"Local motion crossed threshold; "
                                        f"entering event {info.event_id} "
                                        f"(originator={info.originator})"
                                    )
                                    frame_start = frame_counter
                                    if self.save_video:
                                        video_saver = self._spawn_video_saver(
                                            motion_dir, raw, frame.shape,
                                            head, tail, buffer_length, fps,
                                            orin, raspi, cur_clip.name,
                                            frame_counter, info,
                                        )
                                    else:
                                        self.motion_detected = True
                                        self.motion_counter = 0
                            else:
                                num_motion_events = 0
                                if count_delay < delay:
                                    count_delay += 1
                else:
                    # --- Single-cam path: preserved verbatim from today ---
                    if has_motion:
                        num_motion_events += 1
                        count_delay = 0
                        if not self.motion_detected and num_motion_events >= MOTION_EVENTS_THRESH_FRAMES:
                            self.log.info(f"Motion detected with {num_motion_events} events")
                            self.motion_detected = True
                            self.motion_counter = 0
                            frame_start = frame_counter
                            if self.save_video:
                                video_saver = self._spawn_video_saver(
                                    motion_dir, raw, frame.shape, head, tail,
                                    buffer_length, fps, orin, raspi,
                                    cur_clip.name, frame_counter, None,
                                )
                        elif self.motion_counter > MAX_FRAMES_CLIP:
                            self.log.info("Max clip length exceeded")
                            self.stop_video_saving(final=True)
                    else:
                        num_motion_events = 0
                        if count_delay < delay:
                            count_delay += 1
                        else:
                            # If motion has stopped and we have a video saver running, set the stop event
                            if self.motion_detected:
                                self.log.info("Delay exceeded. Motion stopped.")
                                self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                                self.stop_video_saving(final=True)

                if utils.is_check_time(frame_counter, fps):
                    end_time=time.time()
                    elapsed_time = (end_time - start_time) * 1000
                    self.log.info(f"Time elapsed: {elapsed_time:.2f} ms")
                    utils.ping_in_background(self.ping_url)
                frame_counter += 1
        finally:
            try:
                self.dataloader.close()
            except Exception:
                self.log.exception("dataloader.close raised")

            if self.motion_detected:
                self.log.info("No more frames. Motion stopped.")
                try:
                    self.frame_log[cur_clip.name].append((frame_start, frame_counter))
                except Exception:
                    self.log.exception("frame_log append failed")
                try:
                    self.stop_video_saving(final=True)
                except Exception:
                    self.log.exception("stop_video_saving raised")

            # In multi-cam mode, ensure the coordinator always lets this cam
            # leave so a dying cam cannot keep _cams_recording populated.
            # leave_event is idempotent; safe to call even if stop_video_saving
            # already did.
            if multicam and self.coordinator is not None:
                try:
                    self.coordinator.leave_event(self.cam_name)
                except Exception:
                    self.log.exception("coordinator.leave_event raised")

            self.log.info("Joining video saver process in case it has not exited")
            if video_saver and video_saver.is_alive():
                try:
                    video_saver.join()
                except Exception:
                    self.log.exception("video_saver.join raised")
        return self.frame_log
