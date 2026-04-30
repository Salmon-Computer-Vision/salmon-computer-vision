from __future__ import annotations

import csv
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import boto3

from object_detection.utils.utils import safe_float
from object_detection.yolo_ls.shards import TarShardWriter


EXCLUDED_COLUMNS = {
    "Project",
    "Site",
    "Camera",
    "Filename",   # Label Studio task ID, not video filename
    "Date",
    "Time",
    "Notes:",
    "Image Link:",
}

DEFAULT_BUCKET = "prod-salmonvision-edge-assets-labelstudio-source"


@dataclass(frozen=True)
class ConditionRow:
    project: str
    site: str
    camera: str
    labelstudio_task_id: str
    date: str
    time: str
    video_stem: str
    s3_key: str
    conditions: Dict[str, str]
    source_csv: str


@dataclass
class VideoNegativeSample:
    video_stem: str
    s3_key: str
    sampled_frames: List[int]
    total_frames: int
    positive_frames: int
    eligible_negative_frames: int
    conditions: Dict[str, str]
    source_csv: str


@dataclass
class VideoMetadataRecord:
    video_stem: str
    s3_key: str
    fps: float
    nb_frames: int
    duration: float
    width: int
    height: int
    org: str
    site: str
    device: str
    source_csv: str


def normalize_value(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.upper() == "NA":
        return None
    return s


def normalize_date(date_str: str) -> str:
    dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
    return dt.strftime("%Y%m%d")


def normalize_time(time_str: str) -> str:
    # Handles "3:17:05" and "03:17:05"
    dt = datetime.strptime(time_str.strip(), "%H:%M:%S")
    return dt.strftime("%H%M%S")


def construct_video_stem(project: str, site: str, camera: str, date_str: str, time_str: str) -> str:
    return f"{project}-{site}-{camera}_{normalize_date(date_str)}_{normalize_time(time_str)}_M"


def construct_task_s3_key(project: str, site: str, camera: str, video_stem: str) -> str:
    return f"{project}/{site}/{camera}/labelstudio_tasks/{video_stem}.json"


def infer_condition_columns(fieldnames: Sequence[str]) -> List[str]:
    cols: List[str] = []
    for name in fieldnames:
        if name is None:
            continue
        s = name.strip()
        if not s:
            continue
        if s in EXCLUDED_COLUMNS:
            continue
        cols.append(s)
    return cols


def load_condition_rows(csv_paths: Sequence[Path]) -> Tuple[List[ConditionRow], List[str]]:
    rows: List[ConditionRow] = []
    all_fieldnames: List[str] = []

    for csv_path in csv_paths:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for fn in reader.fieldnames:
                    if fn not in all_fieldnames:
                        all_fieldnames.append(fn)

            for raw in reader:
                project = normalize_value(raw.get("Project"))
                site = normalize_value(raw.get("Site"))
                camera = normalize_value(raw.get("Camera"))
                labelstudio_task_id = normalize_value(raw.get("Filename"))
                date_str = normalize_value(raw.get("Date"))
                time_str = normalize_value(raw.get("Time"))

                # Skip blank rows and placeholder rows like "NA"
                if not project or not site or not camera or not date_str or not time_str:
                    continue
                if not labelstudio_task_id:
                    continue

                try:
                    video_stem = construct_video_stem(project, site, camera, date_str, time_str)
                except ValueError:
                    continue

                condition_values: Dict[str, str] = {}
                for col in infer_condition_columns(reader.fieldnames or []):
                    v = normalize_value(raw.get(col))
                    if v is not None:
                        condition_values[col] = v

                row = ConditionRow(
                    project=project,
                    site=site,
                    camera=camera,
                    labelstudio_task_id=labelstudio_task_id,
                    date=date_str,
                    time=time_str,
                    video_stem=video_stem,
                    s3_key=construct_task_s3_key(project, site, camera, video_stem),
                    conditions=condition_values,
                    source_csv=str(csv_path),
                )
                rows.append(row)

    # Dedupe by real video stem
    dedup: Dict[str, ConditionRow] = {}
    for row in rows:
        dedup[row.video_stem] = row

    deduped = list(dedup.values())
    condition_columns = infer_condition_columns(all_fieldnames)
    return deduped, condition_columns


def active_condition_columns(rows: Sequence[ConditionRow], condition_columns: Sequence[str]) -> List[str]:
    keep: List[str] = []
    for col in condition_columns:
        vals = sorted({r.conditions[col] for r in rows if col in r.conditions})
        if len(vals) >= 2:
            keep.append(col)
    return keep


def compute_condition_targets(
    rows: Sequence[ConditionRow],
    condition_columns: Sequence[str],
) -> Tuple[Dict[Tuple[str, str], int], Dict[str, Counter]]:
    per_col_counts: Dict[str, Counter] = {}
    targets: Dict[Tuple[str, str], int] = {}

    for col in condition_columns:
        c = Counter()
        for row in rows:
            if col in row.conditions:
                c[row.conditions[col]] += 1
        if not c:
            continue

        per_col_counts[col] = c
        target = min(c.values())
        for value in c:
            targets[(col, value)] = target

    return targets, per_col_counts


def greedy_select_balanced_rows(
    rows: Sequence[ConditionRow],
    condition_columns: Sequence[str],
) -> Tuple[List[ConditionRow], Dict[Tuple[str, str], int], Dict[str, Counter]]:
    """
    Greedy marginal balancing:
    - each condition column is balanced independently to its rarest category count
    - rows that satisfy multiple deficits are preferred
    """
    targets, per_col_counts = compute_condition_targets(rows, condition_columns)
    deficits = dict(targets)

    remaining = list(rows)
    selected: List[ConditionRow] = []

    def row_score(row: ConditionRow) -> int:
        score = 0
        for col in condition_columns:
            val = row.conditions.get(col)
            if val is None:
                continue
            score += max(deficits.get((col, val), 0), 0)
        return score

    while True:
        best_row = None
        best_score = 0

        for row in remaining:
            score = row_score(row)
            if score > best_score:
                best_score = score
                best_row = row

        if best_row is None or best_score <= 0:
            break

        selected.append(best_row)
        remaining.remove(best_row)

        for col in condition_columns:
            val = best_row.conditions.get(col)
            if val is None:
                continue
            key = (col, val)
            if key in deficits and deficits[key] > 0:
                deficits[key] -= 1

    return selected, targets, per_col_counts


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


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

    duration = safe_float(data.get("metadata_video_duration", data.get("duration", 0.0)), 0.0)
    nb_frames = int(safe_float(data.get("metadata_video_nb_frames"), 0))
    if duration > 0 and nb_frames > 0:
        return nb_frames / duration

    return 0.0


def extract_video_metadata_record(
    item: dict,
    *,
    video_stem: str,
    s3_key: str,
    source_csv: str,
) -> VideoMetadataRecord:
    data = item.get("data") or {}

    return VideoMetadataRecord(
        video_stem=video_stem,
        s3_key=s3_key,
        fps=infer_fps(data),
        nb_frames=int(safe_float(data.get("metadata_video_nb_frames"), 0)),
        duration=safe_float(data.get("metadata_video_duration", data.get("duration", 0.0)), 0.0),
        width=int(safe_float(data.get("metadata_video_width"), 0)),
        height=int(safe_float(data.get("metadata_video_height"), 0)),
        org=str(data.get("metadata_file_organization_reference_string", "")),
        site=str(data.get("metadata_file_site_reference_string", "")),
        device=str(data.get("metadata_file_camera_reference_string", "")),
        source_csv=source_csv,
    )


def cache_task_json(task_json: Any, cache_root: Path, s3_key: str) -> Path:
    out_path = cache_root / s3_key
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(task_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def interpolate_sequence(seq: Iterable[dict]) -> Dict[int, List[Tuple[float, float, float, float]]]:
    kfs = sorted(seq, key=lambda k: int(safe_float(k.get("frame"), 0)))
    frames_boxes: Dict[int, List[Tuple[float, float, float, float]]] = {}

    if not kfs:
        return frames_boxes

    for k in kfs:
        f = int(safe_float(k.get("frame"), -1))
        if f < 0:
            continue
        x = safe_float(k.get("x"))
        y = safe_float(k.get("y"))
        w = safe_float(k.get("width"))
        h = safe_float(k.get("height"))
        frames_boxes.setdefault(f, []).append((x, y, w, h))

    for i in range(len(kfs) - 1):
        k0 = kfs[i]
        k1 = kfs[i + 1]

        f0 = int(safe_float(k0.get("frame"), -1))
        f1 = int(safe_float(k1.get("frame"), -1))
        if f0 < 0 or f1 <= f0:
            continue

        enabled0 = bool(k0.get("enabled", True))
        if not enabled0:
            continue

        x0 = safe_float(k0.get("x"))
        y0 = safe_float(k0.get("y"))
        w0 = safe_float(k0.get("width"))
        h0 = safe_float(k0.get("height"))

        x1 = safe_float(k1.get("x"))
        y1 = safe_float(k1.get("y"))
        w1 = safe_float(k1.get("width"))
        h1 = safe_float(k1.get("height"))

        for f in range(f0 + 1, f1):
            t = (f - f0) / float(f1 - f0)
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            w = w0 + (w1 - w0) * t
            h = h0 + (h1 - h0) * t
            frames_boxes.setdefault(f, []).append((x, y, w, h))

    return frames_boxes


def extract_task_item(task_json: Any, expected_video_stem: str) -> dict:
    if isinstance(task_json, dict):
        return task_json
    if isinstance(task_json, list):
        if len(task_json) == 1:
            return task_json[0]
        for item in task_json:
            data = item.get("data") or {}
            stem = Path(data.get("metadata_file_filename") or data.get("video") or "").stem
            if stem == expected_video_stem:
                return item
        return task_json[0]
    raise ValueError("Unsupported task JSON structure")


def infer_total_frames(item: dict, results: Optional[List[dict]] = None) -> int:
    data = item.get("data") or {}

    n = int(safe_float(data.get("metadata_video_nb_frames"), 0))
    if n > 0:
        return n

    if results:
        for r in results:
            value = r.get("value") or {}
            n = int(safe_float(value.get("framesCount"), 0))
            if n > 0:
                return n

    duration = safe_float(data.get("metadata_video_duration", data.get("duration", 0.0)), 0.0)

    fps = safe_float(data.get("frames_per_second"), 0.0)
    if fps <= 0:
        fps = parse_ffmpeg_rate(data.get("metadata_video_r_frame_rate"))
    if fps <= 0:
        fps = parse_ffmpeg_rate(data.get("metadata_video_avg_frame_rate"))

    if duration > 0 and fps > 0:
        return int(round(duration * fps))

    return 0


def extract_latest_results(
    item: dict,
    result_type: str = "videorectangle",
    from_name: Optional[str] = None,
    to_name: Optional[str] = None,
) -> List[dict]:
    annos = item.get("annotations") or []
    if not annos:
        return []

    latest_ann = max(annos, key=lambda a: parse_ts(a["updated_at"]))
    out: List[dict] = []
    for r in (latest_ann.get("result") or []):
        if r.get("type") != result_type:
            continue
        if from_name is not None and r.get("from_name") != from_name:
            continue
        if to_name is not None and r.get("to_name") != to_name:
            continue
        out.append(r)
    return out


def extract_positive_frames(
    item: dict,
    result_type: str = "videorectangle",
    from_name: Optional[str] = None,
    to_name: Optional[str] = None,
) -> Set[int]:
    results = extract_latest_results(item, result_type=result_type, from_name=from_name, to_name=to_name)
    positive: Set[int] = set()

    for r in results:
        value = r.get("value") or {}
        seq = value.get("sequence") or []
        frame_boxes = interpolate_sequence(seq)
        positive.update(frame_boxes.keys())

    return positive


def stride_offset(video_stem: str, frame_stride: int, frame_offset_mode: str, frame_offset: int) -> int:
    if frame_stride <= 1:
        return 0
    if frame_offset_mode == "fixed":
        return int(frame_offset) % frame_stride
    if frame_offset_mode == "video_hash":
        import zlib
        return zlib.crc32(video_stem.encode("utf-8")) % frame_stride
    raise ValueError(f"Invalid frame_offset_mode: {frame_offset_mode}")


def eligible_negative_frames(
    video_stem: str,
    total_frames: int,
    positive_frames: Set[int],
    frame_stride: int,
    frame_offset_mode: str,
    frame_offset: int,
) -> List[int]:
    off = stride_offset(video_stem, frame_stride, frame_offset_mode, frame_offset)
    return [
        f for f in range(total_frames)
        if (f % frame_stride) == off and f not in positive_frames
    ]


def fetch_task_json(s3_client: Any, bucket: str, key: str) -> Any:
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


def sample_frames(video_stem: str, eligible_frames: Sequence[int], k: int, seed: int) -> List[int]:
    if not eligible_frames or k <= 0:
        return []
    if k >= len(eligible_frames):
        return sorted(eligible_frames)

    rng = random.Random(f"{seed}:{video_stem}")
    return sorted(rng.sample(list(eligible_frames), k))


def create_condition_negative_shards(
    csv_paths: Sequence[Path],
    out_dir: Path,
    *,
    bucket: str = DEFAULT_BUCKET,
    frames_per_video: int = 5,
    frame_stride: int = 3,
    frame_offset_mode: str = "video_hash",
    frame_offset: int = 0,
    shard_size: int = 100000,
    negative_seed: int = 42,
    result_type: str = "videorectangle",
    from_name: Optional[str] = None,
    to_name: Optional[str] = None,
    aws_profile: Optional[str] = None,
    cache_task_json_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_csv = out_dir / "condition_negative_manifest.csv"
    summary_json = out_dir / "condition_negative_summary.json"
    metadata_csv = out_dir / "condition_negative_video_metadata.csv"
    if cache_task_json_dir is not None:
        cache_task_json_dir.mkdir(parents=True, exist_ok=True)

    session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
    s3_client = session.client("s3")

    rows, raw_condition_columns = load_condition_rows(csv_paths)
    condition_columns = active_condition_columns(rows, raw_condition_columns)

    selected_rows, targets, per_col_counts = greedy_select_balanced_rows(rows, condition_columns)

    writer = TarShardWriter(out_dir, shard_size=shard_size, prefix="condition_negatives")

    samples: List[VideoNegativeSample] = []
    failures: List[Dict[str, str]] = []
    metadata_records: List[VideoMetadataRecord] = []

    for row in selected_rows:
        try:
            task_json = fetch_task_json(s3_client, bucket, row.s3_key)

            if cache_task_json_dir is not None:
                cache_task_json(task_json, cache_task_json_dir, row.s3_key)

            item = extract_task_item(task_json, row.video_stem)

            metadata_records.append(
                extract_video_metadata_record(
                    item,
                    video_stem=row.video_stem,
                    s3_key=row.s3_key,
                    source_csv=row.source_csv,
                )
            )

            results = extract_latest_results(
                item,
                result_type=result_type,
                from_name=from_name,
                to_name=to_name,
            )
            total_frames = infer_total_frames(item, results=results)
            if total_frames <= 0:
                failures.append({"video_stem": row.video_stem, "reason": "total_frames_unavailable"})
                continue

            positive = extract_positive_frames(
                item,
                result_type=result_type,
                from_name=from_name,
                to_name=to_name,
            )
            eligible = eligible_negative_frames(
                row.video_stem,
                total_frames,
                positive,
                frame_stride=frame_stride,
                frame_offset_mode=frame_offset_mode,
                frame_offset=frame_offset,
            )

            sampled = sample_frames(
                row.video_stem,
                eligible,
                k=frames_per_video,
                seed=negative_seed,
            )
            if not sampled:
                failures.append({"video_stem": row.video_stem, "reason": "no_eligible_negative_frames"})
                continue

            for frame_idx in sampled:
                writer.write_text(f"{row.video_stem}/frame_{frame_idx:06d}.txt", "")

            samples.append(
                VideoNegativeSample(
                    video_stem=row.video_stem,
                    s3_key=row.s3_key,
                    sampled_frames=sampled,
                    total_frames=total_frames,
                    positive_frames=len(positive),
                    eligible_negative_frames=len(eligible),
                    conditions=row.conditions,
                    source_csv=row.source_csv,
                )
            )
        except Exception as e:
            failures.append({"video_stem": row.video_stem, "reason": repr(e)})

    writer.close()

    with manifest_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "video_stem",
            "s3_key",
            "source_csv",
            "total_frames",
            "positive_frames",
            "eligible_negative_frames",
            "sampled_frames",
        ] + condition_columns
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in samples:
            row = {
                "video_stem": s.video_stem,
                "s3_key": s.s3_key,
                "source_csv": s.source_csv,
                "total_frames": s.total_frames,
                "positive_frames": s.positive_frames,
                "eligible_negative_frames": s.eligible_negative_frames,
                "sampled_frames": " ".join(str(x) for x in s.sampled_frames),
            }
            for col in condition_columns:
                row[col] = s.conditions.get(col, "")
            w.writerow(row)

    with metadata_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "video_stem",
            "s3_key",
            "fps",
            "nb_frames",
            "duration",
            "width",
            "height",
            "org",
            "site",
            "device",
            "source_csv",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rec in metadata_records:
            w.writerow(asdict(rec))

    selected_condition_counts: Dict[str, Counter] = {}
    for col in condition_columns:
        c = Counter()
        for s in samples:
            if col in s.conditions:
                c[s.conditions[col]] += 1
        selected_condition_counts[col] = c

    summary = {
        "bucket": bucket,
        "csv_paths": [str(p) for p in csv_paths],
        "condition_columns": condition_columns,
        "input_rows": len(rows),
        "selected_videos_before_fetch": len(selected_rows),
        "written_videos": len(samples),
        "written_negative_frames": sum(len(s.sampled_frames) for s in samples),
        "frames_per_video": frames_per_video,
        "frame_stride": frame_stride,
        "frame_offset_mode": frame_offset_mode,
        "frame_offset": frame_offset,
        "metadata_csv": str(metadata_csv),
        "cached_task_json_dir": str(cache_task_json_dir) if cache_task_json_dir is not None else "",
        "metadata_records_written": len(metadata_records),
        "targets_by_condition": {
            col: {val: targets[(col, val)] for val in per_col_counts.get(col, {})}
            for col in condition_columns
        },
        "input_counts_by_condition": {
            col: dict(per_col_counts[col]) for col in condition_columns
        },
        "selected_counts_by_condition": {
            col: dict(selected_condition_counts[col]) for col in condition_columns
        },
        "failures": failures,
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return summary
