from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def parse_ffmpeg_rate(rate: Any) -> float:
    if rate is None:
        return 0.0
    if isinstance(rate, (int, float)):
        return float(rate)

    s = str(rate).strip()
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            num = float(a)
            den = float(b)
            return num / den if den else 0.0
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def infer_fps(data: Dict[str, Any]) -> float:
    fps = safe_float(data.get("frames_per_second"), 0.0)
    if fps > 0:
        return fps

    fps = parse_ffmpeg_rate(data.get("metadata_video_r_frame_rate"))
    if fps > 0:
        return fps

    fps = parse_ffmpeg_rate(data.get("metadata_video_avg_frame_rate"))
    if fps > 0:
        return fps

    duration = safe_float(data.get("metadata_video_duration", data.get("duration")), 0.0)
    nb_frames = int(safe_float(data.get("metadata_video_nb_frames"), 0))
    if duration > 0 and nb_frames > 0:
        return nb_frames / duration

    return 0.0


def infer_s3_key(data: Dict[str, Any], video_stem: str) -> str:
    org = data.get("metadata_file_organization_reference_string", "")
    site = data.get("metadata_file_site_reference_string", "")
    cam = data.get("metadata_file_camera_reference_string", "")
    if org and site and cam:
        return f"{org}/{site}/{cam}/motion_vids/{video_stem}.mp4"
    return ""


def iter_task_items(json_dir: Path, pattern: str = "**/*.json") -> Iterable[Dict[str, Any]]:
    for path in sorted(json_dir.glob(pattern)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if isinstance(payload, dict):
            yield payload
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    yield item


def build_video_metadata_index(json_dir: Path) -> List[Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}

    for item in iter_task_items(json_dir):
        data = item.get("data") or {}
        filename = data.get("metadata_file_filename") or data.get("video") or ""
        video_stem = Path(filename).stem
        if not video_stem:
            continue

        row = {
            "video_stem": video_stem,
            "fps": str(infer_fps(data)),
            "nb_frames": str(int(safe_float(data.get("metadata_video_nb_frames"), 0))),
            "duration": str(safe_float(data.get("metadata_video_duration", data.get("duration")), 0.0)),
            "width": str(int(safe_float(data.get("metadata_video_width"), 0))),
            "height": str(int(safe_float(data.get("metadata_video_height"), 0))),
            "org": str(data.get("metadata_file_organization_reference_string", "")),
            "site": str(data.get("metadata_file_site_reference_string", "")),
            "device": str(data.get("metadata_file_camera_reference_string", "")),
            "s3_key": infer_s3_key(data, video_stem),
        }
        rows[video_stem] = row

    return list(rows.values())


def write_video_metadata_index(rows: List[Dict[str, str]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "video_stem",
        "fps",
        "nb_frames",
        "duration",
        "width",
        "height",
        "org",
        "site",
        "device",
        "s3_key",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)

