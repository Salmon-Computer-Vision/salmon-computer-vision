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


@dataclass
class ExtractionStats:
    splits_seen: int = 0
    videos_seen: int = 0
    videos_processed: int = 0
    videos_failed: int = 0
    frames_requested: int = 0
    frames_written: int = 0


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
    bucket: str,
    fps: float = 10.0,
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

    manifest_rows: List[Dict[str, str]] = []

    for split, by_video in split_requests.items():
        for video_stem, frame_indices in by_video.items():
            stats.videos_seen += 1
            stats.frames_requested += len(frame_indices)

            local_video = temp_video_dir / f"{video_stem}.mp4"
            s3_key = ""
            try:
                s3_key = video_stem_to_s3_key(video_stem)
                output_dir = images_root / split / video_stem

                download_s3_video(bucket=bucket, s3_key=s3_key, local_video_path=local_video)

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
