from __future__ import annotations

import csv
import re
import subprocess
import sys
import tarfile
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple

from object_detection.yolo_ls.shards import TarShardWriter
from object_detection.frames.parsing import (
    parse_manifest_relpath,
    split_label_relpath_to_packed_paths,
    video_stem_to_s3_key,
)

from object_detection.utils.utils import safe_float


_DOWNLOAD_OUTPUT_LOCK = threading.Lock()


@dataclass
class ExtractionStats:
    splits_seen: int = 0
    videos_seen: int = 0
    videos_processed: int = 0
    videos_failed: int = 0
    frames_requested: int = 0
    images_written: int = 0
    labels_written: int = 0
    
    images_reused: int = 0
    images_extracted: int = 0

    videos_downloaded: int = 0


@dataclass(frozen=True)
class CachedFrameRef:
    tar_path: Path
    member_name: str


@dataclass(frozen=True)
class PlannedVideo:
    order: int
    split: str
    video_stem: str
    frame_indices: Tuple[int, ...]
    fps: float
    s3_key: str
    local_video: Path
    missing_frames: Tuple[int, ...]


class TarFrameCache:
    """
    Read-only cache of already-extracted image frames stored in tar shards.

    Cache key is:

        (video_stem, frame_idx)

    The original train/val/test split is deliberately ignored. This allows
    a frame that used to be in train to be reused even if a new split puts
    it in val/test.
    """

    FRAME_RE = re.compile(
        r"^frame_(?P<frame>\d+)\.(?:jpg|jpeg|png)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        shard_roots: Iterable[Path],
        *,
        image_ext: str = ".jpg",
    ) -> None:
        self.image_ext = image_ext.lower()
        self._index: Dict[Tuple[str, int], CachedFrameRef] = {}

        roots = [Path(p) for p in shard_roots]

        for root in roots:
            if not root.exists():
                print(f"[frames] reuse cache does not exist, skipping: {root}")
                continue

            tar_paths = sorted(root.glob("*.tar"))

            print(
                f"[frames] indexing reuse cache: "
                f"{root} ({len(tar_paths)} tar files)"
            )

            for tar_path in tar_paths:
                self._index_tar(tar_path)

        print(
            f"[frames] reuse cache contains "
            f"{len(self._index)} image frames"
        )

    def _index_tar(self, tar_path: Path) -> None:
        try:
            with tarfile.open(tar_path, "r") as tf:
                for member in tf:
                    if not member.isfile():
                        continue

                    p = PurePosixPath(member.name)

                    if p.suffix.lower() != self.image_ext:
                        continue

                    # Expected:
                    #
                    # train/<video_stem>/frame_000123.jpg
                    #
                    # We deliberately only care about the final two
                    # components.
                    if len(p.parts) < 2:
                        continue

                    video_stem = p.parts[-2]
                    filename = p.parts[-1]

                    m = self.FRAME_RE.match(filename)
                    if not m:
                        continue

                    frame_idx = int(m.group("frame"))

                    key = (video_stem, frame_idx)

                    # Earlier roots have priority.
                    #
                    # This lets us specify:
                    #
                    #   1. previous per-site shards
                    #   2. legacy combined shards
                    #
                    # and prefer the newer per-site cache.
                    self._index.setdefault(
                        key,
                        CachedFrameRef(
                            tar_path=tar_path,
                            member_name=member.name,
                        ),
                    )

        except tarfile.TarError as e:
            raise RuntimeError(
                f"Could not read reuse tar {tar_path}: {e}"
            ) from e

    def missing_indices(
        self,
        video_stem: str,
        frame_indices: Iterable[int],
    ) -> List[int]:
        """Return requested frame indices that are not present in the cache index."""
        return [
            frame_idx
            for frame_idx in frame_indices
            if (video_stem, frame_idx) not in self._index
        ]

    def get_many(
        self,
        video_stem: str,
        frame_indices: Iterable[int],
    ) -> Dict[int, bytes]:
        """
        Return cached image bytes for as many requested frames as possible.

        Tar files are opened once per group rather than once per frame.
        """
        grouped: Dict[Path, List[Tuple[int, str]]] = defaultdict(list)

        for frame_idx in frame_indices:
            ref = self._index.get((video_stem, frame_idx))

            if ref is not None:
                grouped[ref.tar_path].append(
                    (frame_idx, ref.member_name)
                )

        result: Dict[int, bytes] = {}

        for tar_path, requests in grouped.items():
            with tarfile.open(tar_path, "r") as tf:
                for frame_idx, member_name in requests:
                    member = tf.getmember(member_name)
                    fp = tf.extractfile(member)

                    if fp is None:
                        continue

                    result[frame_idx] = fp.read()

        return result


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
    """
    Download one source MP4 with the AWS CLI.

    Output is captured per process and emitted under a lock so concurrent AWS
    commands do not interleave their warning/error lines. This is particularly
    useful for Glacier warnings, which are later parsed by
    restore_glacier_from_log.sh.
    """
    ensure_dir(local_video_path.parent)

    cmd = [
        "aws", "s3", "cp",
        f"s3://{bucket}/{s3_key}",
        str(local_video_path),
        "--only-show-errors",
    ]

    result = subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Preserve AWS warnings/errors in the pipeline log, but avoid multiple
    # concurrent subprocesses garbling the same line.
    if result.stdout or result.stderr:
        with _DOWNLOAD_OUTPUT_LOCK:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )


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
    reuse_shards_roots: Optional[Iterable[Path]] = None,
    download_workers: int = 8,
) -> ExtractionStats:
    """
    Pack split-aware YOLO labels and image frames into tar shards.

    Source-video downloads are parallelized, but frame extraction and shard
    writing remain single-threaded. This keeps TarShardWriter usage simple and
    avoids running many ffmpeg processes at once.

    Downloads are handled in bounded batches of at most 2 * download_workers
    planned videos, which provides prefetch overlap without allowing an entire
    site's source MP4s to accumulate in temp_video_dir.
    """
    download_workers = int(download_workers)
    if download_workers < 1:
        raise ValueError(
            f"download_workers must be >= 1, got {download_workers}"
        )

    split_requests = load_split_requests(splits_dir, split_names)
    stats = ExtractionStats(splits_seen=len(split_requests))
    metadata_index = merge_video_metadata_csvs(metadata_csv_paths)
    frame_cache = TarFrameCache(
        reuse_shards_roots or [],
        image_ext=image_ext,
    )

    ensure_dir(shards_root)
    ensure_dir(manifests_root)
    ensure_dir(temp_video_dir)

    shard_writers: Dict[str, TarShardWriter] = {}
    for split in split_requests.keys():
        shard_writers[split] = TarShardWriter(
            shards_root,
            shard_size=shard_size,
            prefix=split,
        )

    split_to_image_relpaths: Dict[str, List[str]] = {
        split: []
        for split in split_requests.keys()
    }

    # Store rows by the original deterministic request order. This lets us do
    # metadata/cache planning up front without changing manifest row order.
    manifest_rows_by_order: Dict[int, Dict[str, str]] = {}
    jobs: List[PlannedVideo] = []

    order = 0
    seen_temp_paths: Dict[str, int] = defaultdict(int)

    #
    # Planning pass:
    #   * validate metadata
    #   * determine which videos actually need source downloads from the
    #     lightweight cache index (without reading cached JPEG bytes yet)
    #
    for split, by_video in split_requests.items():
        for video_stem, frame_indices_list in by_video.items():
            order += 1
            frame_indices = tuple(frame_indices_list)

            stats.videos_seen += 1
            stats.frames_requested += len(frame_indices)

            s3_key = ""
            fps = 0.0

            try:
                meta = metadata_index.get(video_stem)
                if meta is None:
                    raise KeyError(
                        f"Missing metadata for video_stem={video_stem}"
                    )

                fps = safe_float(meta.get("fps", ""), 0.0)
                if fps <= 0:
                    raise ValueError(
                        f"Invalid fps for video_stem={video_stem}: "
                        f"{meta.get('fps', '')!r}"
                    )

                s3_key = (meta.get("s3_key") or "").strip()
                if not s3_key:
                    if not bucket:
                        raise ValueError(
                            f"Missing s3_key for video_stem={video_stem}"
                        )
                    s3_key = video_stem_to_s3_key(video_stem)

                missing_frames = tuple(
                    frame_cache.missing_indices(
                        video_stem,
                        frame_indices,
                    )
                )

                # A video should normally occur in exactly one split. If it
                # somehow occurs more than once, avoid concurrent writes to the
                # same temporary path.
                occurrence = seen_temp_paths[video_stem]
                seen_temp_paths[video_stem] += 1
                if occurrence == 0:
                    local_video = temp_video_dir / f"{video_stem}.mp4"
                else:
                    local_video = (
                        temp_video_dir
                        / f"{video_stem}__job_{order:06d}.mp4"
                    )

                jobs.append(
                    PlannedVideo(
                        order=order,
                        split=split,
                        video_stem=video_stem,
                        frame_indices=frame_indices,
                        fps=fps,
                        s3_key=s3_key,
                        local_video=local_video,
                        missing_frames=missing_frames,
                    )
                )

            except Exception as e:
                stats.videos_failed += 1
                manifest_rows_by_order[order] = {
                    "split": split,
                    "video_stem": video_stem,
                    "s3_key": s3_key,
                    "fps": str(fps) if fps > 0 else "",
                    "requested_frames": str(len(frame_indices)),
                    "images_written": "0",
                    "labels_written": "0",
                    "images_reused": "0",
                    "images_extracted": "0",
                    "videos_downloaded": "0",
                    "status": "error",
                    "error": repr(e),
                }

    #
    # Download/extraction pass.
    #
    # A 2x worker batch leaves enough work queued that downloads continue while
    # the main thread extracts/writes earlier videos, while also bounding temp
    # storage to roughly 2 * download_workers source MP4s.
    #
    batch_size = max(1, download_workers * 2)

    for batch_start in range(0, len(jobs), batch_size):
        batch = jobs[batch_start:batch_start + batch_size]

        with ThreadPoolExecutor(
            max_workers=download_workers,
            thread_name_prefix="s3-video",
        ) as executor:
            download_futures: Dict[int, Future[None]] = {}

            for job in batch:
                if not job.missing_frames:
                    continue

                print(
                    f"[frames] {job.video_stem}: "
                    f"{len(job.missing_frames)} frames missing from cache; "
                    f"queued source-video download"
                )

                download_futures[job.order] = executor.submit(
                    download_s3_video,
                    bucket,
                    job.s3_key,
                    job.local_video,
                )

            #
            # Process in deterministic split/video order. Downloads for later
            # videos remain active in the background while the main thread
            # extracts and packs the current one.
            #
            for job in batch:
                writer = shard_writers[job.split]
                video_downloaded = False

                try:
                    future = download_futures.get(job.order)
                    if future is not None:
                        future.result()
                        video_downloaded = True
                        stats.videos_downloaded += 1

                    cached_images = frame_cache.get_many(
                        job.video_stem,
                        job.frame_indices,
                    )

                    if cached_images:
                        print(
                            f"[frames] {job.video_stem}: "
                            f"reusing {len(cached_images)}/"
                            f"{len(job.frame_indices)} cached frames"
                        )

                    # Normally this exactly matches job.missing_frames. Recheck
                    # after reading the tar in case a cache member disappeared
                    # or could not be read after the planning pass.
                    missing_frames = [
                        frame_idx
                        for frame_idx in job.frame_indices
                        if frame_idx not in cached_images
                    ]

                    if missing_frames and not video_downloaded:
                        print(
                            f"[frames] {job.video_stem}: "
                            f"cache changed after planning; downloading source "
                            f"video synchronously"
                        )
                        download_s3_video(
                            bucket=bucket,
                            s3_key=job.s3_key,
                            local_video_path=job.local_video,
                        )
                        video_downloaded = True
                        stats.videos_downloaded += 1

                    for frame_idx in job.frame_indices:
                        label_relpath = (
                            f"{job.video_stem}/"
                            f"frame_{frame_idx:06d}.txt"
                        )

                        image_relpath, packed_label_relpath = (
                            split_label_relpath_to_packed_paths(
                                split=job.split,
                                relpath=label_relpath,
                                image_ext=image_ext,
                            )
                        )

                        image_bytes = cached_images.get(frame_idx)

                        if image_bytes is not None:
                            stats.images_reused += 1
                        else:
                            image_bytes = extract_frame_bytes_ffmpeg(
                                video_path=job.local_video,
                                frame_idx=frame_idx,
                                fps=job.fps,
                                image_ext=image_ext,
                            )
                            stats.images_extracted += 1

                        # Always use the current annotation, even when the image
                        # comes from a previous packed-shard cache.
                        label_text = read_label_text(
                            labels_root,
                            label_relpath,
                        )

                        writer.write_bytes(
                            str(image_relpath),
                            image_bytes,
                        )
                        stats.images_written += 1

                        split_to_image_relpaths[job.split].append(
                            str(image_relpath)
                        )

                        writer.write_text(
                            str(packed_label_relpath),
                            label_text,
                        )
                        stats.labels_written += 1

                    manifest_rows_by_order[job.order] = {
                        "split": job.split,
                        "video_stem": job.video_stem,
                        "s3_key": job.s3_key,
                        "fps": str(job.fps),
                        "requested_frames": str(len(job.frame_indices)),
                        "images_written": str(len(job.frame_indices)),
                        "labels_written": str(len(job.frame_indices)),
                        "images_reused": str(len(cached_images)),
                        "images_extracted": str(len(missing_frames)),
                        "videos_downloaded": str(int(video_downloaded)),
                        "status": "ok",
                        "error": "",
                    }

                    stats.videos_processed += 1

                except Exception as e:
                    stats.videos_failed += 1

                    manifest_rows_by_order[job.order] = {
                        "split": job.split,
                        "video_stem": job.video_stem,
                        "s3_key": job.s3_key,
                        "fps": str(job.fps) if job.fps > 0 else "",
                        "requested_frames": str(len(job.frame_indices)),
                        "images_written": "0",
                        "labels_written": "0",
                        "images_reused": "0",
                        "images_extracted": "0",
                        "videos_downloaded": str(int(video_downloaded)),
                        "status": "error",
                        "error": repr(e),
                    }

                finally:
                    if cleanup_video:
                        try:
                            if job.local_video.exists():
                                job.local_video.unlink()
                        except Exception:
                            pass

    for writer in shard_writers.values():
        writer.close()

    write_split_manifests(
        manifests_root,
        split_to_image_relpaths,
    )
    write_data_yaml(
        manifests_root,
        class_names,
    )

    if manifest_csv is not None:
        ensure_dir(manifest_csv.parent)

        with manifest_csv.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
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
                    "images_reused",
                    "images_extracted",
                    "videos_downloaded",
                    "status",
                    "error",
                ],
            )
            w.writeheader()

            for row_order in sorted(manifest_rows_by_order):
                w.writerow(manifest_rows_by_order[row_order])

    return stats
