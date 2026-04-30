from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
import io
import tarfile

from object_detection.yolo_ls.shards import TarShardWriter
from object_detection.frames.parsing import (
    parse_manifest_relpath,
    split_label_relpath_to_packed_paths,
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
    images_written: int = 0
    labels_written: int = 0

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


def write_split_manifests(
    manifests_root: Path,
    split_to_image_relpaths: Dict[str, List[str]],
) -> None:
    ensure_dir(manifests_root)
    for split, relpaths in split_to_image_relpaths.items():
        out_path = manifests_root / f"{split}.txt"
        relpaths = sorted(relpaths)
        out_path.write_text("\n".join(relpaths) + ("\n" if relpaths else ""), encoding="utf-8")


def write_data_yaml(
    manifests_root: Path,
    class_names: List[str],
) -> None:
    """
    Writes a YOLO-style data.yaml that uses split manifest files.
    """
    lines = [
        "train: train.txt",
        "val: val.txt",
        "test: test.txt",
        "names:",
    ]
    for idx, name in enumerate(class_names):
        lines.append(f"  {idx}: {name}")
    (manifests_root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def read_label_text(labels_root: Path, relpath: str) -> str:
    path = labels_root / relpath
    return path.read_text(encoding="utf-8")


def extract_frame_bytes_ffmpeg(
    video_path: Path,
    frame_idx: int,
    fps: float,
    image_ext: str = ".jpg",
) -> bytes:
    """
    Extract one frame and return the encoded image bytes.
    """
    timestamp = frame_idx / float(fps)

    if image_ext == ".jpg":
        codec_args = ["-f", "image2", "-vcodec", "mjpeg"]
    elif image_ext == ".png":
        codec_args = ["-f", "image2", "-vcodec", "png"]
    else:
        raise ValueError(f"Unsupported image_ext: {image_ext}")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{timestamp:.6f}",
        "-i", str(video_path),
        "-frames:v", "1",
    ] + codec_args + ["pipe:1"]

    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)
    return result.stdout


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


def pack_split_dataset_shards(
    splits_dir: Path,
    labels_root: Path,
    shards_root: Path,
    manifests_root: Path,
    temp_video_dir: Path,
    metadata_csv_paths: Iterable[Path],
    class_names: List[str],
    bucket: str,
    image_ext: str = ".jpg",
    cleanup_video: bool = True,
    split_names: Iterable[str] = ("train", "val", "test"),
    manifest_csv: Optional[Path] = None,
    shard_size: int = 100000,
) -> ExtractionStats:
    """
    Reads split manifests containing label relpaths, e.g.
      HIRMD-.../frame_000123.txt

    Produces sharded paired dataset:
      train/<video_stem>/frame_000123.jpg
      train/<video_stem>/frame_000123.txt
      ...

    Also writes fresh split manifests that point to image relpaths inside the packed layout:
      train/HIRMD-.../frame_000123.jpg
    """
    split_requests = load_split_requests(splits_dir, split_names)
    stats = ExtractionStats(splits_seen=len(split_requests))
    metadata_index = merge_video_metadata_csvs(metadata_csv_paths)

    ensure_dir(shards_root)
    ensure_dir(manifests_root)

    shard_writers: Dict[str, TarShardWriter] = {}
    for split in split_requests.keys():
        shard_writers[split] = TarShardWriter(
            shards_root,
            shard_size=shard_size,
            prefix=split,
        )

    split_to_image_relpaths: Dict[str, List[str]] = {split: [] for split in split_requests.keys()}
    manifest_rows: List[Dict[str, str]] = []

    for split, by_video in split_requests.items():
        writer = shard_writers[split]

        for video_stem, frame_indices in by_video.items():
            stats.videos_seen += 1
            stats.frames_requested += len(frame_indices)

            local_video = temp_video_dir / f"{video_stem}.mp4"
            s3_key = ""
            fps = 0.0

            try:
                meta = metadata_index.get(video_stem)
                if meta is None:
                    raise KeyError(f"Missing metadata for video_stem={video_stem}")

                fps = safe_float(meta.get("fps", ""), 0.0)
                if fps <= 0:
                    raise ValueError(f"Invalid fps for video_stem={video_stem}: {meta.get('fps', '')!r}")

                s3_key = (meta.get("s3_key") or "").strip()
                if not s3_key:
                    if not bucket:
                        raise ValueError(f"Missing s3_key for video_stem={video_stem}")
                    s3_key = video_stem_to_s3_key(video_stem)

                download_s3_video(bucket=bucket, s3_key=s3_key, local_video_path=local_video)

                for frame_idx in frame_indices:
                    label_relpath = f"{video_stem}/frame_{frame_idx:06d}.txt"
                    image_relpath, packed_label_relpath = split_label_relpath_to_packed_paths(
                        split=split,
                        relpath=label_relpath,
                        image_ext=image_ext,
                    )

                    image_bytes = extract_frame_bytes_ffmpeg(
                        video_path=local_video,
                        frame_idx=frame_idx,
                        fps=fps,
                        image_ext=image_ext,
                    )
                    label_text = read_label_text(labels_root, label_relpath)

                    writer.write_bytes(str(image_relpath), image_bytes)
                    split_to_image_relpaths[split].append(str(image_relpath))

                    stats.images_written += 1

                    writer.write_text(str(packed_label_relpath), label_text)
                    stats.labels_written += 1

                stats.videos_processed += 1

                manifest_rows.append({
                    "split": split,
                    "video_stem": video_stem,
                    "s3_key": s3_key,
                    "fps": str(fps),
                    "requested_frames": str(len(frame_indices)),
                    "images_written": str(len(frame_indices)),
                    "labels_written": str(len(frame_indices)),
                    "status": "ok",
                    "error": "",
                })

            except Exception as e:
                stats.videos_failed += 1
                manifest_rows.append({
                    "split": split,
                    "video_stem": video_stem,
                    "s3_key": s3_key,
                    "fps": str(fps) if fps > 0 else "",
                    "requested_frames": str(len(frame_indices)),
                    "images_written": "0",
                    "labels_written": "0",
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

    for writer in shard_writers.values():
        writer.close()

    write_split_manifests(manifests_root, split_to_image_relpaths)
    write_data_yaml(manifests_root, class_names)

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
                    "images_written",
                    "labels_written",
                    "status",
                    "error",
                ],
            )
            w.writeheader()
            for row in manifest_rows:
                w.writerow(row)

    return stats
