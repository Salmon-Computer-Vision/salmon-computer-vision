#!/usr/bin/env python3
"""One-shot local/S3 backfill for pre-compositor multi-camera clips.

The old multi-camera recorder wrote one file per camera directly into
``motion_vids`` using this shape::

    {prefix}_{cam}_{YYYYMMDD_HHMMSS}_E{event}_p{part}_M.mp4

This script inventories a production S3 prefix, downloads the selected date
ranges to a local work directory, groups the old per-camera files, preserves
``--cam-names`` order, end-aligns their frames with the production compositor,
validates the canonical composites, then uploads them to the same S3
``motion_vids/`` prefix. It defaults to a read-only dry run and never deletes
or replaces the original per-camera S3 objects.

Dry run::

    python3 training/tools/backfill_multicam_composites.py --dry-run

Execute after reviewing the dry run::

    python3 training/tools/backfill_multicam_composites.py --execute

Download, composite, and validate without uploading::

    python3 training/tools/backfill_multicam_composites.py \
        --execute --no-upload

Upload already processed local composites without downloading or ffmpeg::

    python3 training/tools/backfill_multicam_composites.py --upload-only
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pysalmcount import clip_compositor as compositor
from pysalmcount import utils


DEFAULT_BUCKET = "prod-salmonvision-edge-assets-labelstudio-source"
DEFAULT_PREFIX = "LAX/fishtrap/jetsonnx-3d/motion_vids/"
DEFAULT_WORK_DIR = Path("/mnt/d/temp_3d_composite")
DEFAULT_SAVE_PREFIX = "LAX-fishtrap-jetsonnx-3d"
DEFAULT_YEAR = 2026
DEFAULT_DATE_RANGES = "07-21:07-25,08-18:08-25"
DEFAULT_CAM_NAMES = ["cam1", "cam2", "cam3"]
DEFAULT_FPS = 10.0
DEFAULT_MAX_CLIP_SECONDS = 120.0

logger = logging.getLogger("backfill_multicam_composites")


@dataclass(frozen=True, order=True)
class GroupKey:
    save_prefix: str
    date: str
    time: str
    event_short: str
    part_number: int


@dataclass
class SourceGroup:
    key: GroupKey
    sources: Dict[str, Path]


@dataclass(frozen=True)
class RemoteObject:
    key: str
    size: int


@dataclass
class RemoteSourceGroup:
    key: GroupKey
    sources: Dict[str, RemoteObject]


def parse_cam_names(value: str) -> List[str]:
    cam_names = [name.strip() for name in value.split(",")]
    if len(cam_names) < 2 or any(not name for name in cam_names):
        raise argparse.ArgumentTypeError(
            "--cam-names requires at least two non-empty comma-separated names"
        )
    if len(set(cam_names)) != len(cam_names):
        raise argparse.ArgumentTypeError("--cam-names must not contain duplicates")
    return cam_names


def parse_date_ranges(value: str, year: int) -> List[Tuple[datetime.date, datetime.date]]:
    ranges: List[Tuple[datetime.date, datetime.date]] = []
    try:
        for item in value.split(","):
            start_text, end_text = (part.strip() for part in item.split(":"))
            start = datetime.datetime.strptime(
                f"{year}-{start_text}", "%Y-%m-%d"
            ).date()
            end = datetime.datetime.strptime(
                f"{year}-{end_text}", "%Y-%m-%d"
            ).date()
            if end < start:
                raise ValueError(f"range ends before it starts: {item}")
            ranges.append((start, end))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--date-ranges must look like 07-21:07-25,08-18:08-25"
        ) from exc
    if not ranges:
        raise argparse.ArgumentTypeError("--date-ranges must not be empty")
    return ranges


def date_is_selected(
    date_value: datetime.date,
    date_ranges: Iterable[Tuple[datetime.date, datetime.date]],
) -> bool:
    return any(start <= date_value <= end for start, end in date_ranges)


def selected_dates(
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
) -> List[datetime.date]:
    dates = set()
    for start, end in date_ranges:
        current = start
        while current <= end:
            dates.add(current)
            current += datetime.timedelta(days=1)
    return sorted(dates)


def run_aws(command: Sequence[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    logger.debug("Running: %s", " ".join(command))
    environment = os.environ.copy()
    environment["AWS_PAGER"] = ""
    return subprocess.run(
        list(command),
        check=True,
        text=True,
        capture_output=capture_output,
        env=environment,
    )


def list_remote_objects(bucket: str, prefix: str) -> List[RemoteObject]:
    logger.info("Inventorying s3://%s/%s", bucket, prefix)
    result = run_aws([
        "aws",
        "s3api",
        "list-objects-v2",
        "--bucket",
        bucket,
        "--prefix",
        prefix,
        "--query",
        "Contents[].[Key,Size]",
        "--output",
        "json",
    ], capture_output=True)
    rows = json.loads(result.stdout or "[]")
    return [
        RemoteObject(key=str(key), size=int(size))
        for key, size in (rows or [])
    ]


def human_size(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def split_source_head(
    head: str,
    cam_names: Sequence[str],
) -> Optional[Tuple[str, str]]:
    """Return ``(save_prefix, cam_name)`` by matching camera names from right."""
    for cam_name in sorted(cam_names, key=len, reverse=True):
        suffix = f"_{cam_name}"
        if head.endswith(suffix):
            save_prefix = head[:-len(suffix)]
            if save_prefix:
                return save_prefix, cam_name
    return None


def source_identity(
    filename: str,
    cam_names: Sequence[str],
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
    save_prefix_override: Optional[str],
) -> Optional[Tuple[GroupKey, str]]:
    match = compositor.PART_TAIL_RE.search(filename)
    if match is None:
        return None
    clip_date = datetime.datetime.strptime(match.group("date"), "%Y%m%d").date()
    if not date_is_selected(clip_date, date_ranges):
        return None

    parsed_head = split_source_head(filename[:match.start()], cam_names)
    if parsed_head is None:
        return None
    inferred_prefix, cam_name = parsed_head
    if save_prefix_override is not None and inferred_prefix != save_prefix_override:
        return None

    return (
        GroupKey(
            save_prefix=save_prefix_override or inferred_prefix,
            date=match.group("date"),
            time=match.group("time"),
            event_short=match.group("event"),
            part_number=int(match.group("part")),
        ),
        cam_name,
    )


def discover_remote_groups(
    remote_objects: Sequence[RemoteObject],
    cam_names: Sequence[str],
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
    save_prefix_override: Optional[str],
) -> List[RemoteSourceGroup]:
    groups: Dict[GroupKey, RemoteSourceGroup] = {}
    for remote_object in remote_objects:
        identity = source_identity(
            Path(remote_object.key).name,
            cam_names,
            date_ranges,
            save_prefix_override,
        )
        if identity is None:
            continue
        key, cam_name = identity
        group = groups.setdefault(
            key,
            RemoteSourceGroup(key=key, sources={}),
        )
        previous = group.sources.get(cam_name)
        if previous is not None:
            raise RuntimeError(
                f"Duplicate remote {cam_name!r} source for {key}: "
                f"{previous.key} and {remote_object.key}"
            )
        group.sources[cam_name] = remote_object
    return [groups[key] for key in sorted(groups)]


def output_filename_for_group(
    key: GroupKey,
    max_clip_seconds: float,
) -> str:
    part_start = datetime.datetime.strptime(
        f"{key.date}_{key.time}", "%Y%m%d_%H%M%S"
    )
    part_start += datetime.timedelta(
        seconds=(key.part_number - 1) * max_clip_seconds
    )
    return f"{key.save_prefix}_{part_start:%Y%m%d_%H%M%S}_M.mp4"


def discover_groups(
    source_dir: Path,
    cam_names: Sequence[str],
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
    save_prefix_override: Optional[str],
) -> Tuple[List[SourceGroup], int]:
    groups: Dict[GroupKey, SourceGroup] = {}
    ignored = 0

    for path in sorted(source_dir.rglob("*_M.mp4")):
        identity = source_identity(
            path.name,
            cam_names,
            date_ranges,
            save_prefix_override,
        )
        if identity is None:
            continue
        key, cam_name = identity
        group = groups.setdefault(key, SourceGroup(key=key, sources={}))
        previous = group.sources.get(cam_name)
        if previous is not None:
            raise RuntimeError(
                f"Duplicate {cam_name!r} source for {key}: {previous} and {path}"
            )
        group.sources[cam_name] = path

    return [groups[key] for key in sorted(groups)], ignored


def read_source_metadata(path: Path, source_metadata_dir: Path) -> dict:
    metadata_path = source_metadata_dir / f"{path.stem}.json"
    try:
        with metadata_path.open() as file_obj:
            payload = json.load(file_obj)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def default_source_metadata_dir(source_dir: Path) -> Path:
    known_names = {
        "motion_vids": "motion_vids_metadata",
        "motion_vids_parts": "motion_vids_parts_metadata",
        "motion_vids_backup": "motion_vids_metadata_backup",
    }
    metadata_name = known_names.get(
        source_dir.name,
        f"{source_dir.name}_metadata",
    )
    return source_dir.parent / metadata_name


def build_job(
    group: SourceGroup,
    cam_names: Sequence[str],
    source_metadata_dir: Path,
    output_dir: Path,
    fps: float,
    max_clip_seconds: float,
) -> compositor.CompositeJob:
    metadata_items = [
        read_source_metadata(path, source_metadata_dir)
        for path in group.sources.values()
    ]

    event_ids = {
        str(item["event_id"])
        for item in metadata_items
        if item.get("event_id")
    }
    if len(event_ids) > 1:
        raise RuntimeError(
            f"Conflicting event IDs for {group.key}: {sorted(event_ids)}"
        )
    event_id = next(
        iter(event_ids),
        (
            f"backfill_{group.key.date}T{group.key.time}_"
            f"{group.key.event_short}"
        ),
    )

    part_start_candidates: List[datetime.datetime] = []
    for item in metadata_items:
        raw_part_start = item.get("part_start_ts")
        if not raw_part_start:
            continue
        try:
            part_start = datetime.datetime.fromisoformat(str(raw_part_start))
        except ValueError:
            continue
        if part_start.tzinfo is not None:
            part_start_candidates.append(part_start)

    if part_start_candidates:
        part_start_ts = part_start_candidates[0]
        if any(
            abs((candidate - part_start_ts).total_seconds()) >= 1
            for candidate in part_start_candidates[1:]
        ):
            raise RuntimeError(f"Conflicting part start times for {group.key}")
    else:
        # Interpret the timestamp exactly as it appeared in the old filename.
        # Calling astimezone() on a naive datetime applies the container's local
        # timezone and means composite_output_path() reproduces that wall time.
        part_start_ts = datetime.datetime.strptime(
            f"{group.key.date}_{group.key.time}", "%Y%m%d_%H%M%S"
        ).astimezone()
        part_start_ts += datetime.timedelta(
            seconds=(group.key.part_number - 1) * max_clip_seconds
        )

    sources = [
        compositor.CompositeSource(
            cam_name=cam_name,
            path=group.sources.get(cam_name),
        )
        for cam_name in cam_names
    ]
    return compositor.CompositeJob(
        event_id=event_id,
        part_number=group.key.part_number,
        part_start_ts=part_start_ts,
        sources=sources,
        out_dir=output_dir,
        save_prefix=group.key.save_prefix,
        fps=fps,
        sonar=False,
    )


def canonical_output_path(job: compositor.CompositeJob) -> Path:
    timestamp = job.part_start_ts.astimezone().strftime("%Y%m%d_%H%M%S")
    return job.out_dir / f"{job.save_prefix}_{timestamp}_M.mp4"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as file_obj:
        json.dump(payload, file_obj, indent=4)


def run_backfill_job(
    job: compositor.CompositeJob,
    source_metadata_dir: Path,
    output_metadata_dir: Path,
    delete_sources: bool,
) -> Path:
    """Run production-equivalent alignment/encoding without implicit cleanup."""
    out_path = canonical_output_path(job)
    if out_path.exists():
        raise FileExistsError(out_path)

    alignment = compositor.calculate_end_alignment(job)
    tmp_path = out_path.with_name(f".{out_path.stem}.backfill.tmp.mp4")
    command = compositor.build_ffmpeg_cmd(job, tmp_path, alignment=alignment)
    try:
        subprocess.run(
            command,
            check=True,
            preexec_fn=lambda: os.nice(10),
        )
        if out_path.exists():
            raise FileExistsError(out_path)
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    metadata = utils.get_video_metadata(out_path)
    if metadata is None:
        raise RuntimeError(f"Could not probe completed backfill: {out_path}")

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
        "frame_alignment": "end",
        "source_frame_counts": alignment.source_frame_counts,
        "start_frame_trim": alignment.start_frame_trims,
        "aligned_frame_count": alignment.aligned_frame_count,
        "backfilled": True,
    })
    write_json(output_metadata_dir / f"{out_path.stem}.json", payload)

    if delete_sources:
        for source in job.sources:
            if source.path is None:
                continue
            source.path.unlink(missing_ok=True)
            (source_metadata_dir / f"{source.path.stem}.json").unlink(
                missing_ok=True
            )

    return out_path


def download_selected_objects(
    bucket: str,
    prefix: str,
    source_dir: Path,
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
    cam_names: Sequence[str],
) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "aws",
        "s3",
        "sync",
        f"s3://{bucket}/{prefix}",
        str(source_dir),
        "--exclude",
        "*",
    ]
    for date_value in selected_dates(date_ranges):
        for cam_name in cam_names:
            command.extend([
                "--include",
                (
                    f"*_{cam_name}_{date_value:%Y%m%d}_*"
                    "_E*_p*_M.mp4"
                ),
            ])
    command.extend(["--only-show-errors", "--no-progress"])
    run_aws(command)


def validate_downloads(
    selected_objects: Sequence[RemoteObject],
    prefix: str,
    source_dir: Path,
) -> None:
    failures = []
    for remote_object in selected_objects:
        relative_key = remote_object.key[len(prefix):]
        local_path = source_dir / relative_key
        try:
            local_size = local_path.stat().st_size
        except FileNotFoundError:
            failures.append(f"missing: {local_path}")
            continue
        if local_size != remote_object.size:
            failures.append(
                f"size mismatch: {local_path} local={local_size} "
                f"remote={remote_object.size}"
            )
    if failures:
        sample = "\n".join(failures[:20])
        raise RuntimeError(
            f"Downloaded object validation failed for {len(failures)} files:\n"
            f"{sample}"
        )


def validate_composite(path: Path, expected_rows: int) -> None:
    metadata = utils.get_video_metadata(path)
    if metadata is None:
        raise RuntimeError(f"Could not probe generated composite: {path}")
    expected_height = 720 * expected_rows
    if metadata.width != 1280 or metadata.height != expected_height:
        raise RuntimeError(
            f"Unexpected composite geometry for {path}: "
            f"{metadata.width}x{metadata.height}; expected 1280x{expected_height}"
        )
    if metadata.nb_frames <= 0:
        raise RuntimeError(f"Generated composite has no frames: {path}")


def stage_for_upload(source: Path, upload_dir: Path) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    staged = upload_dir / source.name
    if staged.exists():
        if staged.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Conflicting upload-stage file: {staged}")
        return staged
    try:
        os.link(source, staged)
    except OSError:
        shutil.copy2(source, staged)
    return staged


def discover_local_backfilled_composites(
    output_dir: Path,
    output_metadata_dir: Path,
    cam_names: Sequence[str],
    date_ranges: Sequence[Tuple[datetime.date, datetime.date]],
    save_prefix: Optional[str],
) -> Tuple[List[Path], int]:
    """Find outputs created by this backfill for the selected source dates."""
    if not output_dir.exists():
        raise RuntimeError(f"Local composite directory does not exist: {output_dir}")

    selected = []
    ignored = 0
    for path in sorted(output_dir.glob("*_M.mp4")):
        if compositor.PART_TAIL_RE.search(path.name) is not None:
            ignored += 1
            continue
        metadata_path = output_metadata_dir / f"{path.stem}.json"
        try:
            with metadata_path.open() as file_obj:
                metadata = json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Ignoring local output without usable backfill metadata: %s",
                path,
            )
            ignored += 1
            continue
        if metadata.get("backfilled") is not True:
            ignored += 1
            continue
        if metadata.get("layout") != "vstack":
            raise RuntimeError(f"Backfill metadata has wrong layout: {metadata_path}")
        if metadata.get("cam_order") != list(cam_names):
            raise RuntimeError(
                f"Backfill camera order differs from --cam-names: {metadata_path}"
            )

        source_clips = metadata.get("source_clips")
        if not isinstance(source_clips, list) or not any(
            source_path is not None
            and source_identity(
                Path(str(source_path)).name,
                cam_names,
                date_ranges,
                save_prefix,
            ) is not None
            for source_path in source_clips
        ):
            ignored += 1
            continue

        validate_composite(path, len(cam_names))
        selected.append(path)
    return selected, ignored


def upload_staged_composites(bucket: str, prefix: str, upload_dir: Path) -> None:
    run_aws([
        "aws",
        "s3",
        "sync",
        str(upload_dir),
        f"s3://{bucket}/{prefix}",
        "--exclude",
        "*",
        "--include",
        "*_M.mp4",
        "--only-show-errors",
        "--no-progress",
    ])


def ensure_upload_targets_are_absent(
    bucket: str,
    prefix: str,
    staged_paths: Sequence[Path],
) -> None:
    current_keys = {
        remote.key
        for remote in list_remote_objects(bucket, prefix)
    }
    conflicts = [
        f"{prefix}{path.name}"
        for path in staged_paths
        if f"{prefix}{path.name}" in current_keys
    ]
    if conflicts:
        raise RuntimeError(
            "Refusing to overwrite canonical S3 objects that appeared after "
            "the initial inventory:\n" + "\n".join(conflicts[:20])
        )


def verify_uploaded_composites(
    bucket: str,
    prefix: str,
    staged_paths: Sequence[Path],
) -> None:
    refreshed = {
        remote.key: remote.size
        for remote in list_remote_objects(bucket, prefix)
    }
    failures = []
    for path in staged_paths:
        key = f"{prefix}{path.name}"
        remote_size = refreshed.get(key)
        local_size = path.stat().st_size
        if remote_size != local_size:
            failures.append(
                f"{key}: local={local_size}, remote={remote_size}"
            )
    if failures:
        raise RuntimeError(
            "Upload verification failed:\n" + "\n".join(failures[:20])
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download selected production multi-camera clips, vertically "
            "composite them locally, and upload canonical outputs. The "
            "default mode is a read-only dry run."
        )
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"S3 bucket (default: {DEFAULT_BUCKET})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"S3 motion_vids prefix (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help=f"Local workspace (default: {DEFAULT_WORK_DIR})",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_YEAR,
        help=f"Year of the historical filename dates (default: {DEFAULT_YEAR})",
    )
    parser.add_argument(
        "--cam-names",
        type=parse_cam_names,
        default=DEFAULT_CAM_NAMES,
        help=(
            "Comma-separated top-to-bottom camera order "
            f"(default: {','.join(DEFAULT_CAM_NAMES)})"
        ),
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_FPS,
        help=f"Composite output FPS (default: {DEFAULT_FPS:g})",
    )
    parser.add_argument(
        "--date-ranges",
        default=DEFAULT_DATE_RANGES,
        help=(
            "Inclusive MM-DD:MM-DD ranges (default: "
            f"{DEFAULT_DATE_RANGES})"
        ),
    )
    parser.add_argument(
        "--save-prefix",
        default=DEFAULT_SAVE_PREFIX,
        help=f"Canonical device filename prefix (default: {DEFAULT_SAVE_PREFIX})",
    )
    parser.add_argument(
        "--max-clip-seconds",
        type=float,
        default=DEFAULT_MAX_CLIP_SECONDS,
        help=(
            "Fallback spacing for p002+ when old metadata has no part_start_ts "
            "(default: 120)"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory and report the plan without local or S3 writes (default)",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Download, composite, validate, and upload",
    )
    mode.add_argument(
        "--upload-only",
        action="store_true",
        help=(
            "Validate and upload existing local backfill composites without "
            "downloading sources or running ffmpeg"
        ),
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help=(
            "With --execute, download, composite, and validate locally but "
            "do not stage or upload composites to S3"
        ),
    )
    parser.add_argument(
        "--skip-space-check",
        action="store_true",
        help="Do not enforce the conservative local free-space check",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.fps <= 0:
        parser.error("--fps must be positive")
    if args.max_clip_seconds <= 0:
        parser.error("--max-clip-seconds must be positive")
    if args.no_upload and not args.execute:
        parser.error("--no-upload requires --execute")

    try:
        date_ranges = parse_date_ranges(args.date_ranges, args.year)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if shutil.which("aws") is None:
        parser.error("The AWS CLI is required but was not found")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        parser.error("ffmpeg and ffprobe are required but were not found")

    prefix = args.prefix.strip("/") + "/"
    work_dir = args.work_dir.resolve()
    source_dir = work_dir / "downloaded_motion_vids"
    source_metadata_dir = work_dir / "downloaded_motion_vids_metadata"
    output_dir = work_dir / "motion_vids"
    output_metadata_dir = work_dir / "motion_vids_metadata"

    remote_objects = list_remote_objects(args.bucket, prefix)
    remote_keys = {remote.key for remote in remote_objects}

    if args.upload_only:
        local_composites, ignored_local = discover_local_backfilled_composites(
            output_dir=output_dir,
            output_metadata_dir=output_metadata_dir,
            cam_names=args.cam_names,
            date_ranges=date_ranges,
            save_prefix=args.save_prefix,
        )
        pending_uploads = [
            path
            for path in local_composites
            if f"{prefix}{path.name}" not in remote_keys
        ]
        already_remote = len(local_composites) - len(pending_uploads)
        logger.info("S3 destination: s3://%s/%s", args.bucket, prefix)
        logger.info("Local composite directory: %s", output_dir)
        logger.info(
            "Upload-only plan: %d validated local composites to upload, "
            "%d already in S3, %d unrelated local files ignored",
            len(pending_uploads),
            already_remote,
            ignored_local,
        )
        if not pending_uploads:
            logger.info("No local composites need uploading")
            return 0

        run_tag = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        upload_dir = (
            work_dir
            / "upload_motion_vids"
            / f"upload_only_{run_tag}_{os.getpid()}"
        )
        staged_paths = [
            stage_for_upload(path, upload_dir)
            for path in pending_uploads
        ]
        ensure_upload_targets_are_absent(
            args.bucket,
            prefix,
            staged_paths,
        )
        upload_staged_composites(args.bucket, prefix, upload_dir)
        verify_uploaded_composites(
            args.bucket,
            prefix,
            staged_paths,
        )
        logger.info(
            "Upload-only complete: verified %d composites in S3; no source "
            "clips were downloaded and ffmpeg was not run",
            len(staged_paths),
        )
        return 0

    remote_groups = discover_remote_groups(
        remote_objects=remote_objects,
        cam_names=args.cam_names,
        date_ranges=date_ranges,
        save_prefix_override=args.save_prefix,
    )
    selected_objects = sorted(
        {
            remote.key: remote
            for group in remote_groups
            for remote in group.sources.values()
        }.values(),
        key=lambda remote: remote.key,
    )

    ready_group_keys = []
    existing_remote = 0
    missing_row_groups = 0
    groups_by_date: Dict[str, int] = {}
    output_claims: Dict[str, List[GroupKey]] = {}
    for group in remote_groups:
        output_name = output_filename_for_group(
            group.key,
            args.max_clip_seconds,
        )
        output_claims.setdefault(output_name, []).append(group.key)
        output_key = f"{prefix}{output_name}"
        groups_by_date[group.key.date] = groups_by_date.get(group.key.date, 0) + 1
        if output_key in remote_keys:
            existing_remote += 1
            continue
        ready_group_keys.append(group.key)
        if len(group.sources) < len(args.cam_names):
            missing_row_groups += 1

    output_collisions = {
        output_name: keys
        for output_name, keys in output_claims.items()
        if len(keys) > 1
    }

    selected_size = sum(remote.size for remote in selected_objects)
    logger.info("S3 source: s3://%s/%s", args.bucket, prefix)
    logger.info("Local work directory: %s", work_dir)
    logger.info("Top-to-bottom camera order: %s", args.cam_names)
    logger.info(
        "Selected inclusive ranges: %s",
        ", ".join(f"{start} through {end}" for start, end in date_ranges),
    )
    logger.info(
        "Selected downloads: %d objects, %s",
        len(selected_objects),
        human_size(selected_size),
    )
    logger.info(
        "Source groups by filename date: %s",
        ", ".join(
            f"{date_value}={count}"
            for date_value, count in sorted(groups_by_date.items())
        ),
    )
    logger.info(
        "Composite plan: %d to create, %d already in S3, "
        "%d with one or more black rows, %d filename collisions",
        len(ready_group_keys),
        existing_remote,
        missing_row_groups,
        len(output_collisions),
    )
    if output_collisions:
        for output_name, keys in list(sorted(output_collisions.items()))[:20]:
            logger.error("COLLISION %s claimed by %s", output_name, keys)

    if not args.execute:
        logger.info(
            "Dry run only: no directories, downloads, composites, or uploads "
            "were created. Re-run with --execute after reviewing this plan."
        )
        return 0

    if not selected_objects:
        logger.warning("No S3 motion clips matched the requested dates")
        return 0
    if output_collisions:
        raise RuntimeError(
            f"Refusing to execute with {len(output_collisions)} canonical "
            "filename collisions; inspect the dry-run collision report"
        )

    if not args.skip_space_check:
        probe_path = work_dir
        while not probe_path.exists() and probe_path != probe_path.parent:
            probe_path = probe_path.parent
        free_bytes = shutil.disk_usage(probe_path).free
        required_bytes = selected_size * 2
        if free_bytes < required_bytes:
            raise RuntimeError(
                f"Insufficient free space under {probe_path}: "
                f"{human_size(free_bytes)} available, conservative estimate "
                f"is {human_size(required_bytes)}. Free space or use "
                "--skip-space-check after checking manually."
            )

    work_dir.mkdir(parents=True, exist_ok=True)
    source_metadata_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_metadata_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading selected S3 motion clips")
    download_selected_objects(
        bucket=args.bucket,
        prefix=prefix,
        source_dir=source_dir,
        date_ranges=date_ranges,
        cam_names=args.cam_names,
    )
    validate_downloads(selected_objects, prefix, source_dir)
    logger.info("Validated %d downloaded objects", len(selected_objects))

    local_groups, ignored = discover_groups(
        source_dir=source_dir,
        cam_names=args.cam_names,
        date_ranges=date_ranges,
        save_prefix_override=args.save_prefix,
    )
    local_group_map = {group.key: group for group in local_groups}
    missing_local_groups = [
        key for key in ready_group_keys if key not in local_group_map
    ]
    if missing_local_groups:
        raise RuntimeError(
            f"Downloaded data is missing {len(missing_local_groups)} planned "
            f"groups; first missing group: {missing_local_groups[0]}"
        )

    run_tag = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    upload_dir = work_dir / "upload_motion_vids" / f"{run_tag}_{os.getpid()}"
    staged_paths: List[Path] = []
    completed = 0
    resumed = 0
    failed = 0

    for index, key in enumerate(ready_group_keys, start=1):
        group = local_group_map[key]
        try:
            job = build_job(
                group=group,
                cam_names=args.cam_names,
                source_metadata_dir=source_metadata_dir,
                output_dir=output_dir,
                fps=args.fps,
                max_clip_seconds=args.max_clip_seconds,
            )
            out_path = canonical_output_path(job)
            expected_name = output_filename_for_group(
                key,
                args.max_clip_seconds,
            )
            if out_path.name != expected_name:
                raise RuntimeError(
                    f"Output naming disagreement for {key}: "
                    f"{out_path.name} != {expected_name}"
                )

            if out_path.exists():
                validate_composite(out_path, len(args.cam_names))
                resumed += 1
                logger.info(
                    "[%d/%d] Reusing validated local output %s",
                    index,
                    len(ready_group_keys),
                    out_path,
                )
            else:
                present = [
                    source.cam_name for source in job.sources if source.path
                ]
                missing = [
                    source.cam_name
                    for source in job.sources
                    if source.path is None
                ]
                logger.info(
                    "[%d/%d] Compositing present=%s missing=%s -> %s",
                    index,
                    len(ready_group_keys),
                    present,
                    missing,
                    out_path,
                )
                run_backfill_job(
                    job=job,
                    source_metadata_dir=source_metadata_dir,
                    output_metadata_dir=output_metadata_dir,
                    delete_sources=False,
                )
                validate_composite(out_path, len(args.cam_names))
                completed += 1
            if not args.no_upload:
                staged_paths.append(stage_for_upload(out_path, upload_dir))
        except Exception:
            failed += 1
            logger.exception("Backfill failed; source group retained: %s", key)

    logger.info(
        "Local processing summary: %d created, %d resumed, %d failed, "
        "%d ignored",
        completed,
        resumed,
        failed,
        ignored,
    )

    if args.no_upload:
        logger.info(
            "Local-only mode complete: validated composites remain in %s; "
            "nothing was uploaded to S3",
            output_dir,
        )
    elif staged_paths:
        logger.info("Uploading %d validated composites", len(staged_paths))
        ensure_upload_targets_are_absent(
            args.bucket,
            prefix,
            staged_paths,
        )
        upload_staged_composites(args.bucket, prefix, upload_dir)
        verify_uploaded_composites(
            args.bucket,
            prefix,
            staged_paths,
        )
        logger.info("Verified %d uploaded composites in S3", len(staged_paths))
    else:
        logger.info("No new composites were staged for upload")

    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    raise SystemExit(main())
