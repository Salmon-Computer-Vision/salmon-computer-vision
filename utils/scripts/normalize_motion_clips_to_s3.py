#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

SODAFL_RE = re.compile(
    r"""
    ^
    (?P<prefix>SodaFL)
    -
    (?P<mm>\d{2})
    (?P<dd>\d{2})
    (?P<yy>\d{2})
    -
    (?P<index>\d{3})
    \.
    (?P<ext>avi|mp4|m4v|mov)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


MOTION_RE = re.compile(
    r"""
    ^(?!\._)
    (?P<day>\d{2})
    -
    (?P<month>\d{2})
    -
    (?P<year>\d{4})
    \s+
    (?P<hour>\d{1,2})
    (?:
        -
        (?P<minute>\d{2})
        -
        (?P<second>\d{2})
    )?
    \s+
    (?P<label>[MC])
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class ClipInfo:
    src_path: Path
    recorded_at: datetime
    label: str
    duration_seconds: float | None = None

    @property
    def timestamp(self) -> str:
        return self.recorded_at.strftime("%Y%m%d_%H%M%S")

@dataclass(frozen=True)
class SodaFLParsed:
    src_path: Path
    date: datetime
    index: int

def _parse_ffmpeg_rate(rate: str) -> float:
    if not rate:
        return 0.0

    if "/" in rate:
        num_s, den_s = rate.split("/", 1)
        try:
            num = float(num_s)
            den = float(den_s)
            return num / den if den else 0.0
        except Exception:
            return 0.0

    try:
        return float(rate)
    except Exception:
        return 0.0


def _run_ffprobe_json(path: Path, timeout: float) -> dict:
    import json

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return json.loads(result.stdout)


def probe_duration_seconds(path: Path, timeout: float = 20.0) -> float:
    """
    Return video duration in seconds.

    Tries:
      1. format.duration
      2. video stream duration
      3. nb_frames / frame_rate fallback

    Raises RuntimeError if duration cannot be determined.
    """
    try:
        data = _run_ffprobe_json(path, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffprobe timed out after {timeout:.1f}s") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"ffprobe failed: {stderr}") from e

    fmt = data.get("format") or {}
    duration = fmt.get("duration")
    if duration not in (None, "", "N/A"):
        try:
            d = float(duration)
            if d > 0:
                return d
        except Exception:
            pass

    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue

        duration = stream.get("duration")
        if duration not in (None, "", "N/A"):
            try:
                d = float(duration)
                if d > 0:
                    return d
            except Exception:
                pass

        nb_frames = stream.get("nb_frames")
        rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
        fps = _parse_ffmpeg_rate(str(rate or ""))
        if nb_frames not in (None, "", "N/A") and fps > 0:
            try:
                n = float(nb_frames)
                d = n / fps
                if d > 0:
                    return d
            except Exception:
                pass

    raise RuntimeError("Could not determine duration from ffprobe metadata")


def run_cmd(cmd: list[str], dry_run: bool = False) -> None:
    print("+ " + " ".join(str(x) for x in cmd), flush=True)
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required executable not found in PATH: {name}")


def parse_hhmmss(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Expected HH:MM:SS, got {text!r}")

    hh, mm, ss = [int(x) for x in parts]
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ValueError(f"Invalid HH:MM:SS value: {text!r}")

    return hh, mm, ss


def parse_clip_filename(path: Path, *, date_order: str = "dmy") -> Optional[ClipInfo]:
    """
    Parse examples like:
      04-07-2025 15-17-26 M upper club fish box.m4v
      04-07-2025 13 C upper club fish box.m4v

    For motion clips, expects label M. If minute/second are absent, defaults to 00:00.
    """
    m = MOTION_RE.search(path.name)
    if not m:
        return None

    label = m.group("label").upper()
    if label != "M":
        return None

    a = int(m.group("day"))
    b = int(m.group("month"))
    year = int(m.group("year"))

    if date_order == "dmy":
        day, month = a, b
    elif date_order == "mdy":
        month, day = a, b
    else:
        raise ValueError(f"Unsupported date_order: {date_order}")

    hour = int(m.group("hour"))
    minute = int(m.group("minute") or 0)
    second = int(m.group("second") or 0)

    try:
        dt = datetime(year, month, day, hour, minute, second)
    except ValueError as e:
        raise ValueError(f"Could not parse date/time from {path.name!r}: {e}") from e

    return ClipInfo(src_path=path, recorded_at=dt, label=label)


def parse_sodafl_filename(path: Path) -> Optional[SodaFLParsed]:
    """
    Parse SodaFL-MMDDYY-INDEX.ext filenames.

    Example:
      SodaFL-010322-001.avi

    Middle portion is MMDDYY. The final HHMMSS is assigned later using
    cumulative durations within each day.
    """
    m = SODAFL_RE.match(path.name)
    if not m:
        return None

    month = int(m.group("mm"))
    day = int(m.group("dd"))
    yy = int(m.group("yy"))
    index = int(m.group("index"))

    year = 2000 + yy
    date = datetime(year, month, day, 0, 0, 0)

    return SodaFLParsed(src_path=path, date=date, index=index)


def build_sodafl_clips_contiguous(
    paths: list[Path],
    *,
    ffprobe_timeout: float = 20.0,
    skip_bad_duration: bool = True,
) -> tuple[list[ClipInfo], int]:
    parsed: list[SodaFLParsed] = []
    parse_errors = 0

    for path in paths:
        try:
            p = parse_sodafl_filename(path)
            if p is not None:
                parsed.append(p)
        except Exception as e:
            parse_errors += 1
            print(f"[WARN] Could not parse SodaFL filename {path}: {e}", file=sys.stderr)

    by_date: dict[datetime, list[SodaFLParsed]] = {}
    for p in parsed:
        by_date.setdefault(p.date, []).append(p)

    clips: list[ClipInfo] = []

    for date, items in sorted(by_date.items(), key=lambda kv: kv[0]):
        items.sort(key=lambda x: (x.index, x.src_path.name))

        elapsed = 0.0
        for item in items:
            try:
                duration = probe_duration_seconds(item.src_path, timeout=ffprobe_timeout)

            except Exception as e:
                parse_errors += 1
                msg = f"[WARN] Could not probe duration for {item.src_path}: {e}"
                if skip_bad_duration:
                    print(msg + " -- skipping file", file=sys.stderr)
                    continue
                raise RuntimeError(msg) from e

            recorded_at = date + timedelta(seconds=int(round(elapsed)))

            clips.append(
                ClipInfo(
                    src_path=item.src_path,
                    recorded_at=recorded_at,
                    label="M",
                    duration_seconds=duration,
                )
            )

            elapsed += duration

    return clips, parse_errors


def iter_video_files(root: Path, exts: set[str]) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def make_output_name(orgid: str, site: str, device: str, recorded_at: datetime) -> str:
    timestamp = recorded_at.strftime("%Y%m%d_%H%M%S")
    return f"{orgid}-{site}-{device}_{timestamp}_M.mp4"


def make_s3_key(orgid: str, site: str, device: str, output_name: str) -> str:
    return f"{orgid}/{site}/{device}/motion_vids/{output_name}"


def encode_clip_segment(
    *,
    src_path: Path,
    dst_path: Path,
    start_seconds: float,
    segment_seconds: int,
    crf: int,
    preset: str,
    dry_run: bool,
) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",

        # Helps with older AVI files with broken/missing timestamps.
        "-fflags",
        "+genpts",

        # Input first, then -ss for accurate seek.
        "-i",
        str(src_path),
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        str(segment_seconds),

        "-map",
        "0:v:0",

        # Reset timestamps after cutting.
        "-vf",
        "setpts=PTS-STARTPTS",

        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",

        # Avoid weird negative timestamp behavior.
        "-avoid_negative_ts",
        "make_zero",

        "-an",
        str(dst_path),
    ]
    run_cmd(cmd, dry_run=dry_run)


def s3_object_exists(bucket: str, key: str, dry_run: bool = False) -> bool:
    if dry_run:
        return False

    cmd = [
        "aws",
        "s3api",
        "head-object",
        "--bucket",
        bucket,
        "--key",
        key,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def upload_to_s3(
    *,
    local_path: Path,
    bucket: str,
    key: str,
    storage_class: Optional[str],
    dry_run: bool,
) -> None:
    uri = f"s3://{bucket}/{key}"

    cmd = [
        "aws",
        "s3",
        "cp",
        str(local_path),
        uri,
        "--only-show-errors",
    ]

    if storage_class:
        cmd.extend(["--storage-class", storage_class])

    run_cmd(cmd, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-encode M-labeled motion clips to H.264 MP4 and upload to S3."
    )
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)

    parser.add_argument("--bucket", required=True)
    parser.add_argument("--orgid", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--device", default="pi-0")

    parser.add_argument("--date-order", choices=["dmy", "mdy"], default="dmy")
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=120,
        help="Maximum duration of each output segment in seconds",
    )
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--exts", nargs="*", default=[".m4v", ".mp4", ".mov", ".avi"])

    parser.add_argument(
        "--filename-format",
        choices=["legacy", "sodafl", "auto"],
        default="auto",
        help="Filename parser to use. auto tries both legacy M/C format and SodaFL-MMDDYY-INDEX.",
    )
    parser.add_argument(
        "--skip-bad-duration",
        dest="skip_bad_duration",
        action="store_true",
        default=True,
        help="Skip videos whose duration cannot be probed",
    )
    parser.add_argument(
        "--no-skip-bad-duration",
        dest="skip_bad_duration",
        action="store_false",
        help="Fail if any video duration cannot be probed",
    )
    parser.add_argument(
        "--ffprobe-timeout",
        type=float,
        default=20.0,
        help="Timeout in seconds for probing each video duration",
    )

    parser.add_argument(
        "--collision",
        choices=["skip", "overwrite", "error"],
        default="skip",
        help="What to do if the S3 key already exists.",
    )
    parser.add_argument(
        "--storage-class",
        default=None,
        help="Optional S3 storage class, e.g. STANDARD_IA.",
    )
    parser.add_argument("--keep-local", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")
    require_binary("aws")

    input_root = args.input_root
    work_dir = args.work_dir
    exts = {x.lower() if x.startswith(".") else f".{x.lower()}" for x in args.exts}

    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")

    all_video_paths = sorted(iter_video_files(input_root, exts))

    clips: list[ClipInfo] = []
    parse_errors = 0

    if args.filename_format == "sodafl":
        clips, parse_errors = build_sodafl_clips_contiguous(
            all_video_paths,
            ffprobe_timeout=args.ffprobe_timeout,
            skip_bad_duration=args.skip_bad_duration,
        )

    else:
        for path in all_video_paths:
            try:
                clip = None

                if args.filename_format in {"legacy", "auto"}:
                    clip = parse_clip_filename(path, date_order=args.date_order)

                if clip is None and args.filename_format == "auto":
                    parsed = parse_sodafl_filename(path)
                    if parsed is not None:
                        duration = probe_duration_seconds(path, timeout=args.ffprobe_timeout)
                        clip = ClipInfo(
                            src_path=path,
                            recorded_at=parsed.date,
                            label="M",
                            duration_seconds=duration,
                        )

            except Exception as e:
                parse_errors += 1
                print(f"[WARN] Could not parse {path}: {e}", file=sys.stderr)
                continue

            if clip is not None:
                clips.append(clip)

    print(f"Found {len(clips)} M-labeled clips under {input_root}")
    if parse_errors:
        print(f"Parse errors: {parse_errors}")

    uploaded = 0
    skipped = 0
    failed = 0

    for clip in clips:
        print(f"\n[CLIP] {clip.src_path}")

        try:
            duration = clip.duration_seconds
            if duration is None:
                duration = probe_duration_seconds(clip.src_path, timeout=args.ffprobe_timeout)
            n_segments = max(1, int((duration + args.segment_seconds - 1) // args.segment_seconds))

            print(f"[INFO] duration={duration:.2f}s segments={n_segments}")

            for seg_idx in range(n_segments):
                start_seconds = seg_idx * args.segment_seconds
                segment_recorded_at = clip.recorded_at + timedelta(seconds=start_seconds)

                output_name = make_output_name(
                    args.orgid,
                    args.site,
                    args.device,
                    segment_recorded_at,
                )
                s3_key = make_s3_key(args.orgid, args.site, args.device, output_name)
                local_mp4 = work_dir / output_name

                print(f"[SEG ] {seg_idx + 1}/{n_segments} start={start_seconds:.1f}s")
                print(f"[OUT ] {output_name}")
                print(f"[S3  ] s3://{args.bucket}/{s3_key}")

                exists = s3_object_exists(args.bucket, s3_key, dry_run=args.dry_run)

                if exists and args.collision == "skip":
                    print("[SKIP] S3 object already exists")
                    skipped += 1
                    continue
                if exists and args.collision == "error":
                    raise RuntimeError(f"S3 object already exists: s3://{args.bucket}/{s3_key}")

                encode_clip_segment(
                    src_path=clip.src_path,
                    dst_path=local_mp4,
                    start_seconds=start_seconds,
                    segment_seconds=args.segment_seconds,
                    crf=args.crf,
                    preset=args.preset,
                    dry_run=args.dry_run,
                )

                upload_to_s3(
                    local_path=local_mp4,
                    bucket=args.bucket,
                    key=s3_key,
                    storage_class=args.storage_class,
                    dry_run=args.dry_run,
                )

                uploaded += 1

                if not args.keep_local and not args.dry_run:
                    local_mp4.unlink(missing_ok=True)

        except Exception as e:
            failed += 1
            print(f"[ERROR] Failed processing {clip.src_path}: {e}", file=sys.stderr)

    print("\nDone.")
    print(f"uploaded={uploaded}")
    print(f"skipped={skipped}")
    print(f"failed={failed}")


if __name__ == "__main__":
    main()
