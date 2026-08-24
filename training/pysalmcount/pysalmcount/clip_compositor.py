#!/usr/bin/env python3
"""Post-process synchronized per-camera motion clips into one vertical clip."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import secrets
import subprocess
from dataclasses import asdict, dataclass
from multiprocessing import Process
from pathlib import Path
from typing import List, Optional, Sequence

from pysalmcount import utils


logger = logging.getLogger(__name__)

MOTION_VIDS_METADATA_DIR = "motion_vids_metadata"
MOTION_VIDS_PARTS_METADATA = "motion_vids_parts_metadata"

PART_TAIL_RE = re.compile(
    r"_(?P<date>\d{8})_(?P<time>\d{6})_E(?P<event>[0-9a-f]{6})_"
    r"p(?P<part>\d{3})_M\.mp4$"
)


@dataclass(frozen=True)
class CompositeSource:
    cam_name: str
    path: Optional[Path]
    pre_roll_frames: int


@dataclass(frozen=True)
class CompositeJob:
    event_id: str
    part_number: int
    part_start_ts: datetime.datetime
    sources: List[CompositeSource]
    out_dir: Path
    save_prefix: str
    fps: float
    sonar: bool


def composite_output_path(job: CompositeJob) -> Path:
    """Reserve a canonical output name without ever overwriting a clip."""
    if job.part_start_ts.tzinfo is None:
        raise ValueError("CompositeJob.part_start_ts must be timezone-aware")

    timestamp = job.part_start_ts.astimezone().strftime("%Y%m%d_%H%M%S")
    base = f"{job.save_prefix}_{timestamp}"
    filename = Path(job.out_dir) / f"{base}_M.mp4"
    if not filename.exists():
        return filename

    collided = filename
    now_tag = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    filename = Path(job.out_dir) / f"collision_{base}_{now_tag}_M.mp4"
    while filename.exists():
        token = secrets.token_hex(2)
        filename = Path(job.out_dir) / (
            f"collision_{base}_{now_tag}_{token}_M.mp4"
        )
    logger.error(
        "Composite path already exists (unexpected collision): %s; preserving "
        "it and writing the new clip to %s",
        collided,
        filename,
    )
    return filename


def _effective_source_duration(source: CompositeSource, trim_frames: int, fps: float) -> float:
    if source.path is None:
        return 0.0
    metadata = utils.get_video_metadata(source.path)
    if metadata is None:
        raise RuntimeError(f"Could not probe composite source: {source.path}")
    return max(0.0, metadata.duration - (trim_frames / fps))


def build_ffmpeg_cmd(job: CompositeJob, out_path: Path) -> List[str]:
    """Build the ffmpeg command for a frame-aligned vertical composition."""
    if not job.sources:
        raise ValueError("CompositeJob.sources must not be empty")
    if job.fps <= 0:
        raise ValueError(f"CompositeJob.fps must be positive, got {job.fps}")

    present = [source for source in job.sources if source.path is not None]
    if not present:
        raise ValueError("At least one composite source must be present")

    p_min = min(source.pre_roll_frames for source in present)
    trims = [
        max(0, source.pre_roll_frames - p_min) if source.path is not None else 0
        for source in job.sources
    ]
    durations = [
        _effective_source_duration(source, trim, job.fps)
        for source, trim in zip(job.sources, trims)
        if source.path is not None
    ]
    max_duration = max(durations)
    if max_duration <= 0:
        raise RuntimeError("Composite sources have no video after pre-roll trimming")

    fps_str = f"{job.fps:g}"
    cmd = ["ffmpeg", "-hide_banner", "-y", "-fflags", "+genpts"]
    for source in job.sources:
        if source.path is None:
            cmd.extend([
                "-f",
                "lavfi",
                "-t",
                f"{max_duration:.6f}",
                "-i",
                f"color=c=black:s=1280x720:r={fps_str}",
            ])
        else:
            cmd.extend(["-i", str(source.path)])

    filters = []
    for index, trim in enumerate(trims):
        filters.append(
            f"[{index}:v]trim=start_frame={trim},setpts=PTS-STARTPTS,"
            f"scale=1280:-2,setsar=1,fps={fps_str}[v{index}]"
        )
    inputs = "".join(f"[v{index}]" for index in range(len(job.sources)))
    filters.append(f"{inputs}vstack=inputs={len(job.sources)}[outv]")

    cmd.extend([
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[outv]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        "-avoid_negative_ts",
        "make_zero",
        "-threads",
        "2",
        str(out_path),
    ])
    return cmd


def _parts_metadata_path(source_path: Path) -> Path:
    return (
        source_path.parent.parent
        / MOTION_VIDS_PARTS_METADATA
        / f"{source_path.stem}.json"
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as file_obj:
        json.dump(payload, file_obj, indent=4)


def run_composite(job: CompositeJob) -> Path:
    """Create, probe, publish, and clean up one composite job."""
    job.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = composite_output_path(job)
    tmp_path = out_path.with_name(f".{out_path.stem}.tmp.mp4")
    cmd = build_ffmpeg_cmd(job, tmp_path)

    logger.info(
        "Compositing event=%s part=%d cameras=%s to %s",
        job.event_id,
        job.part_number,
        [source.cam_name for source in job.sources],
        out_path,
    )
    try:
        subprocess.run(
            cmd,
            check=True,
            preexec_fn=lambda: os.nice(10),
        )
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    metadata = utils.get_video_metadata(out_path)
    if metadata is None:
        raise RuntimeError(f"Could not probe completed composite: {out_path}")

    present = [source for source in job.sources if source.path is not None]
    p_min = min(source.pre_roll_frames for source in present)
    pre_roll_trim = [
        max(0, source.pre_roll_frames - p_min) if source.path is not None else 0
        for source in job.sources
    ]
    payload = asdict(metadata)
    payload.update({
        "event_id": job.event_id,
        "part_number": job.part_number,
        "part_start_ts": job.part_start_ts.isoformat(),
        "cam_order": [source.cam_name for source in job.sources],
        "layout": "vstack",
        "source_clips": [
            str(source.path) if source.path is not None else None
            for source in job.sources
        ],
        "pre_roll_trim": pre_roll_trim,
    })
    metadata_path = (
        out_path.parent.parent / MOTION_VIDS_METADATA_DIR / f"{out_path.stem}.json"
    )
    _write_json(metadata_path, payload)

    if job.sonar:
        # Import lazily to avoid a module cycle: motion_detect_stream imports
        # CompositeJob for its completion barrier.
        from pysalmcount.motion_detect_stream import SONAR_DEVICE_SETTINGS, VideoSaver

        settings_path = VideoSaver.filename_to_device_settings_filepath(out_path)
        _write_json(settings_path, SONAR_DEVICE_SETTINGS)

    for source in present:
        assert source.path is not None
        metadata_path = _parts_metadata_path(source.path)
        try:
            source.path.unlink()
        except FileNotFoundError:
            logger.warning("Composite source was already absent: %s", source.path)
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            logger.warning("Composite source metadata was absent: %s", metadata_path)

    logger.info("Composite complete: %s", out_path)
    return out_path


class CompositorWorker(Process):
    """Serialize ffmpeg work so composite jobs cannot compete with each other."""

    def __init__(self, job_queue):
        super().__init__(name="ClipCompositor", daemon=False)
        self.job_queue = job_queue

    def run(self) -> None:
        while True:
            job = self.job_queue.get()
            if job is None:
                return
            try:
                run_composite(job)
            except Exception:
                logger.exception(
                    "Composite failed for event=%s part=%s; source clips retained",
                    getattr(job, "event_id", "unknown"),
                    getattr(job, "part_number", "unknown"),
                )


def _cam_name_from_head(head: str, cam_names: Sequence[str]) -> Optional[str]:
    for cam_name in sorted(cam_names, key=len, reverse=True):
        if head == cam_name or head.endswith(f"_{cam_name}"):
            return cam_name
    return None


def find_stale_composite_jobs(
    parts_dir: Path,
    cam_names: Sequence[str],
    out_dir: Path,
    save_prefix: str,
    fps: float,
    sonar: bool,
    stale_after_seconds: float,
    *,
    now: Optional[float] = None,
) -> List[CompositeJob]:
    """Recover complete per-camera clips left behind by a prior process."""
    parts_dir = Path(parts_dir)
    if not parts_dir.exists():
        return []
    if now is None:
        now = datetime.datetime.now().timestamp()

    groups = {}
    for path in sorted(parts_dir.glob("*_M.mp4")):
        match = PART_TAIL_RE.search(path.name)
        if match is None:
            logger.warning("Ignoring unrecognized composite part filename: %s", path)
            continue
        head = path.name[:match.start()]
        cam_name = _cam_name_from_head(head, cam_names)
        if cam_name is None:
            logger.warning("Could not recover camera name from composite part: %s", path)
            continue
        tail_event = match.group("event")
        tail_part = int(match.group("part"))
        tail_date = match.group("date")
        tail_time = match.group("time")

        event_id = None
        part_start_ts = None
        pre_roll_frames = 0
        metadata_path = _parts_metadata_path(path)
        try:
            with open(metadata_path) as file_obj:
                metadata = json.load(file_obj)
            event_id = str(metadata["event_id"])
            part_number = int(metadata["part_number"])
            part_start_ts = datetime.datetime.fromisoformat(metadata["part_start_ts"])
            pre_roll_frames = int(metadata["pre_roll_frames"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            event_id = None
            part_start_ts = None
            pre_roll_frames = 0
            logger.warning(
                "Recovering stale composite part without usable metadata; "
                "pre-roll trim defaults to zero: %s",
                path,
            )
        else:
            if part_number != tail_part:
                logger.error(
                    "Parts metadata disagrees with filename for %s; using "
                    "filename part=%d instead of metadata part=%d",
                    path,
                    tail_part,
                    part_number,
                )
            if part_start_ts.tzinfo is None:
                logger.error(
                    "Parts metadata has naive part_start_ts for %s; using "
                    "the filename timestamp",
                    path,
                )
                part_start_ts = None

        key = (tail_event, tail_part, tail_date, tail_time)
        group = groups.setdefault(key, {
            "event_ids": set(),
            "part_start_ts": None,
            "sources": {},
            "mtimes": [],
        })
        if event_id is not None:
            group["event_ids"].add(event_id)
        if part_start_ts is not None:
            group["part_start_ts"] = part_start_ts.astimezone(
                datetime.timezone.utc
            )
        group["sources"][cam_name] = CompositeSource(
            cam_name=cam_name,
            path=path,
            pre_roll_frames=pre_roll_frames,
        )
        group["mtimes"].append(path.stat().st_mtime)

    jobs = []
    for (tail_event, part_number, tail_date, tail_time), group in sorted(
        groups.items()
    ):
        if any(
            now - mtime < stale_after_seconds
            for mtime in group["mtimes"]
        ):
            continue
        if len(group["event_ids"]) > 1:
            logger.error(
                "Ignoring stale part group with conflicting event IDs: %s",
                sorted(group["event_ids"]),
            )
            continue
        event_id = next(
            iter(group["event_ids"]),
            f"recovered_{tail_date}T{tail_time}_{tail_event}",
        )
        part_start_ts = group["part_start_ts"] or datetime.datetime.strptime(
            f"{tail_date}_{tail_time}", "%Y%m%d_%H%M%S"
        ).astimezone().astimezone(datetime.timezone.utc)
        present_sources = list(group["sources"].values())
        missing_pre_roll = min(
            (source.pre_roll_frames for source in present_sources),
            default=0,
        )
        sources = [
            group["sources"].get(
                cam_name,
                CompositeSource(cam_name, None, missing_pre_roll),
            )
            for cam_name in cam_names
        ]
        jobs.append(CompositeJob(
            event_id=event_id,
            part_number=part_number,
            part_start_ts=part_start_ts,
            sources=sources,
            out_dir=Path(out_dir),
            save_prefix=save_prefix,
            fps=float(fps),
            sonar=bool(sonar),
        ))
    return jobs
