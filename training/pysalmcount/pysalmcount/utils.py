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

def parse_ffmpeg_video_stream_probe(video_stream: dict) -> None | VideoMetadata:
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
        logging.error(f"Could not parse video_stream: {video_stream}, error {e}")
        return None


def get_video_metadata(video_filepath: Path) -> None | VideoMetadata:
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
            logging.error(f"No video stream found")
            return None

        return parse_ffmpeg_video_stream_probe(video_stream)

    except ffmpeg.Error as e:
        logging.error(f"Error occured: {e}")
        return None
