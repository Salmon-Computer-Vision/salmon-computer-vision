from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from object_detection.frames.parsing import (
    label_relpath_to_image_relpath,
    parse_manifest_relpath,
    video_stem_to_s3_key,
)

from object_detection.utils.utils import safe_float


@dataclass
class ExtractionStats:
    splits_seen: int = 0
    videos_seen: int = 0
    videos_processed: int = 0
    videos_failed: int = 0
    frames_requested: int = 0
    frames_written: int = 0

def load_video_metadata_index(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            video_stem = (row.get("video_stem") or "").strip()
            if not video_stem:
                continue
            out[video_stem] = dict(row)
    return out

def merge_video_metadata_csvs(paths: Iterable[Path]) -> Dict[str, Dict[str, str]]:
    """
    Merge metadata CSVs by video_stem.
    Later CSVs overwrite earlier CSVs on conflicts.
    """
    merged: Dict[str, Dict[str, str]] = {}
    for path in paths:
        current = load_video_metadata_index(path)
        for video_stem, row in current.items():
            if video_stem in merged:
                prev = merged[video_stem]
                if prev.get("fps") != row.get("fps") or prev.get("s3_key") != row.get("s3_key"):
                    print(
                        f"[frames] warning: overriding metadata for {video_stem} "
                        f"from fps={prev.get('fps')} s3_key={prev.get('s3_key')} "
                        f"to fps={row.get('fps')} s3_key={row.get('s3_key')}"
                    )
            merged[video_stem] = row
    return merged

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_split_manifest(path: Path) -> List[str]:
    lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines


def load_split_requests(splits_dir: Path, split_names: Iterable[str]) -> Dict[str, Dict[str, List[int]]]:
    """
    Returns:
      {
        "train": {video_stem: [frame_idx, ...], ...},
        "val":   {...},
        "test":  {...},
      }
    """
    out: Dict[str, Dict[str, List[int]]] = {}

    for split in split_names:
        manifest = splits_dir / f"{split}.txt"
        if not manifest.exists():
            continue

        by_video: Dict[str, List[int]] = {}
        for line in read_split_manifest(manifest):
            video_stem, frame_idx = parse_manifest_relpath(line)
            by_video.setdefault(video_stem, []).append(frame_idx)

        # dedupe + sort
        by_video = {k: sorted(set(v)) for k, v in by_video.items()}
        out[split] = by_video

    return out


def download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
    ensure_dir(local_video_path.parent)
    cmd = [
        "aws", "s3", "cp",
        f"s3://{bucket}/{s3_key}",
        str(local_video_path),
    ]
    subprocess.run(cmd, check=True)


def extract_frame_ffmpeg(
    video_path: Path,
    frame_idx: int,
    fps: float,
    output_path: Path,
    overwrite: bool = False,
) -> bool:
    """
    Extract one frame using timestamp = frame_idx / fps.
    """
    if output_path.exists() and not overwrite:
        return False

    ensure_dir(output_path.parent)
    timestamp = frame_idx / float(fps)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{timestamp:.6f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        "-y" if overwrite else "-n",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return True


def extract_video_frames_for_split(
    video_path: Path,
    frame_indices: Iterable[int],
    output_dir: Path,
    fps: float,
    image_ext: str = ".jpg",
    overwrite: bool = False,
) -> int:
    written = 0
    for frame_idx in sorted(set(frame_indices)):
        out_path = output_dir / f"frame_{frame_idx:06d}"
        out_path = out_path.with_suffix(image_ext)

        did_write = extract_frame_ffmpeg(
            video_path=video_path,
            frame_idx=frame_idx,
            fps=fps,
            output_path=out_path,
            overwrite=overwrite,
        )
        if did_write or out_path.exists():
            written += 1
    return written


def extract_split_dataset_images(
    splits_dir: Path,
    images_root: Path,
    temp_video_dir: Path,
    metadata_csv_paths: Iterable[Path],
    bucket: str = "",
    image_ext: str = ".jpg",
    overwrite: bool = False,
    cleanup_video: bool = True,
    split_names: Iterable[str] = ("train", "val", "test"),
    manifest_csv: Optional[Path] = None,
) -> ExtractionStats:
    """
    Reads split manifests:
      splits_dir/train.txt
      splits_dir/val.txt
      splits_dir/test.txt

    Writes:
      images_root/train/<video_stem>/frame_XXXXXX.jpg
      images_root/val/<video_stem>/frame_XXXXXX.jpg
      images_root/test/<video_stem>/frame_XXXXXX.jpg
    """
    split_requests = load_split_requests(splits_dir, split_names)
    stats = ExtractionStats(splits_seen=len(split_requests))
    metadata_index = merge_video_metadata_csvs(metadata_csv_paths)

    manifest_rows: List[Dict[str, str]] = []

    for split, by_video in split_requests.items():
        for video_stem, frame_indices in by_video.items():
            stats.videos_seen += 1
            stats.frames_requested += len(frame_indices)

            local_video = temp_video_dir / f"{video_stem}.mp4"
            s3_key = ""
            try:
                video_meta = metadata_index.get(video_stem)
                if not video_meta:
                    raise KeyError(f"Missing metadata for {video_stem}")

                fps = float(video_meta["fps"])
                if fps <= 0:
                    raise ValueError(f"Invalid fps for {video_stem}: {video_meta['fps']}")

                meta = metadata_index.get(video_stem)
                if meta is None:
                    raise KeyError(f"Missing metadata for video_stem={video_stem}")

                fps = safe_float(meta.get("fps", ""), 0.0)
                if fps <= 0:
                    raise ValueError(f"Invalid fps for video_stem={video_stem}: {meta.get('fps', '')!r}")

                s3_key = (meta.get("s3_key") or "").strip()
                if not s3_key:
                    if not bucket:
                        raise ValueError(f"Missing s3_key for video_stem={video_stem} and no bucket fallback available")
                    s3_key = video_stem_to_s3_key(video_stem)

                # If s3_key already contains bucket-like prefix, keep bucket only for aws cli command construction.
                output_dir = images_root / split / video_stem

                # If caller did not pass bucket explicitly, infer it from known default in your project usage.
                effective_bucket = bucket or "prod-salmonvision-edge-assets-labelstudio-source"

                download_s3_video(bucket=effective_bucket, s3_key=s3_key, local_video_path=local_video)

                frames_written = extract_video_frames_for_split(
                    video_path=local_video,
                    frame_indices=frame_indices,
                    output_dir=output_dir,
                    fps=fps,
                    image_ext=image_ext,
                    overwrite=overwrite,
                )

                stats.videos_processed += 1
                stats.frames_written += frames_written

                manifest_rows.append({
                    "split": split,
                    "video_stem": video_stem,
                    "s3_key": s3_key,
                    "fps": str(fps),
                    "requested_frames": str(len(frame_indices)),
                    "written_frames": str(frames_written),
                    "status": "ok",
                    "error": "",
                })

            except Exception as e:
                stats.videos_failed += 1
                manifest_rows.append({
                    "split": split,
                    "video_stem": video_stem,
                    "s3_key": s3_key,
                    "fps": str(meta.get("fps", "")) if "meta" in locals() and meta is not None else "",
                    "requested_frames": str(len(frame_indices)),
                    "written_frames": "0",
                    "status": "error",
                    "error": repr(e),
                })

            finally:
                if cleanup_video:
                    try:
                        if local_video.exists():
                            local_video.unlink()
                    except Exception:
                        pass

    if manifest_csv is not None:
        ensure_dir(manifest_csv.parent)
        with manifest_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "split",
                    "video_stem",
                    "s3_key",
                    "fps",
                    "requested_frames",
                    "written_frames",
                    "status",
                    "error",
                ],
            )
            w.writeheader()
            for row in manifest_rows:
                w.writerow(row)

    return stats
