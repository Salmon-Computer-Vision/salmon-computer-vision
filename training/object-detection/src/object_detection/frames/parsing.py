from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from object_detection.utils.utils import parse_video_stem


def split_label_relpath_to_packed_paths(
    split: str,
    relpath: str,
    image_ext: str = ".jpg",
) -> Tuple[Path, Path]:
    """
    Convert a split manifest label entry like:
      HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt

    into packed dataset paths:
      train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.jpg
      train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt
    """
    p = Path(relpath.strip())
    label_rel = Path(split) / p
    image_rel = label_rel.with_suffix(image_ext)
    return image_rel, label_rel


def parse_frame_idx(label_filename: str) -> Optional[int]:
    m = re.match(r"^frame_(\d+)\.txt$", label_filename)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def video_stem_to_s3_key(video_stem: str) -> str:
    meta = parse_video_stem(video_stem)
    if meta is None:
        raise ValueError("Could not parse video stem: %s" % video_stem)
    return f"{meta['org']}/{meta['site']}/{meta['device']}/motion_vids/{video_stem}.mp4"


def parse_manifest_relpath(relpath: str) -> Tuple[str, int]:
    """
    Input line example:
      HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt
    Returns:
      (video_stem, frame_idx)
    """
    p = Path(relpath.strip())
    if len(p.parts) < 2:
        raise ValueError("Invalid manifest relpath: %s" % relpath)

    video_stem = p.parts[0]
    frame_idx = parse_frame_idx(p.name)
    if frame_idx is None:
        raise ValueError("Invalid frame filename: %s" % p.name)

    return video_stem, frame_idx


def label_relpath_to_image_relpath(relpath: str, image_ext: str = ".jpg") -> Path:
    p = Path(relpath.strip())
    return p.with_suffix(image_ext)
