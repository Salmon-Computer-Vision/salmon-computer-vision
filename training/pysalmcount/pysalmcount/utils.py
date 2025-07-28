import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import requests
import threading

import ffmpeg

from typing import Union

logger = logging.getLogger(__name__)

@dataclass
class VideoMetadata:
    duration: float
    codec_name: str
    nb_frames: int
    width: int
    height: int
    start_time: float
    avg_frame_rate: str
    r_frame_rate: str

def parse_ffmpeg_video_stream_probe(video_stream: dict) -> Union[None, VideoMetadata]:
    """
    Parses the video_stream dict into a VideoMetadata.
    """
    try:
        codec_name = str(video_stream["codec_name"])
        duration = float(video_stream["duration"])
        nb_frames = int(video_stream["nb_frames"])
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        start_time = float(video_stream["start_time"])
        avg_frame_rate = str(video_stream["avg_frame_rate"])
        r_frame_rate = str(video_stream["r_frame_rate"])

        return VideoMetadata(
            duration=duration,
            codec_name=codec_name,
            nb_frames=nb_frames,
            width=width,
            height=height,
            start_time=start_time,
            avg_frame_rate=avg_frame_rate,
            r_frame_rate=r_frame_rate,
        )

    except Exception as e:
        logger.error(f"Could not parse video_stream: {video_stream}, error {e}")
        return None


def get_video_metadata(video_filepath: Path) -> Union[None, VideoMetadata]:
    """
    Returns VideoMetadata of a video_filepath using ffmpeg or None if it encounters
    an error.
    Parameters:
    video_filepath (Path): Path to the MP4 file.
    Returns:
    VideoMetadata: see dataclass definition for the returned keys.
    """
    try:
        # Probe the video file to get metadata
        probe = ffmpeg.probe(video_filepath)
        # Extract the video stream
        video_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "video"),
            None,
        )
        if video_stream is None:
            logger.error(f"No video stream found")
            return None

        return parse_ffmpeg_video_stream_probe(video_stream)

    except ffmpeg.Error as e:
        logger.error(f"Error occured: {e}")
        logger.error(f"{e.stderr}")
        return None

def is_check_time(frame_counter, fps):
    HEALTH_CHECKS_LEN = 30 # Frequency of healthchecks in seconds

    return frame_counter % (fps * HEALTH_CHECKS_LEN) == 0

def send_ping(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Ping sent successfully")
    except requests.RequestException as e:
        logger.info("Ping failed: %s", e)

def ping_in_background(url):
    t = threading.Thread(target=send_ping, args=(url,), daemon=True)
    t.start()
    return t
