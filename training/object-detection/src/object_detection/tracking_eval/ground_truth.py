from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from object_detection.utils.utils import safe_float
from object_detection.yolo_ls.parsing import (
    coord_mode as infer_coord_mode,
    load_class_map_from_yolo_yaml,
    load_json_paths_from_site_manifest,
    to_yolo,
)


VALID_COORD_MODES = {"auto", "percent", "normalized", "pixel"}


@dataclass(frozen=True)
class EvalVideo:
    split: str
    video_stem: str
    site: str
    local_video_path: str


@dataclass(frozen=True)
class TrackFrame:
    frame_idx: int
    x: float
    y: float
    width: float
    height: float
    rotation: float
    is_keyframe: bool
    keyframe_enabled: Optional[bool]


@dataclass
class AnnotationCandidate:
    video_stem: str
    site: str
    item: dict
    annotation: Optional[dict]
    annotation_updated_at: str
    source_json: Path


@dataclass
class BuildStats:
    videos_selected: int = 0
    videos_with_tracks: int = 0
    videos_zero_gt: int = 0
    videos_condition_negative: int = 0
    videos_annotation_not_found: int = 0
    tracks_written: int = 0
    gt_rows_written: int = 0
    synthetic_track_uids: int = 0
    unknown_class_tracks: int = 0
    rotated_rows: int = 0


def _parse_ts(value: object) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _task_video_stem(item: dict) -> str:
    data = item.get("data") or {}
    value = data.get("metadata_file_filename") or data.get("video") or ""
    if not value:
        return ""
    return Path(str(value).split("?", 1)[0]).stem


def _iter_task_items(path: Path) -> Iterable[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        yield payload
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
    else:
        raise ValueError(f"Label Studio export must be object or list: {path}")


def _latest_annotation(item: dict) -> Optional[dict]:
    annotations = [a for a in (item.get("annotations") or []) if isinstance(a, dict)]
    if not annotations:
        return None
    return max(annotations, key=lambda a: _parse_ts(a.get("updated_at")))


def _annotation_timestamp(annotation: Optional[dict]) -> str:
    if annotation is None:
        return ""
    return str(annotation.get("updated_at") or "")


def _candidate_is_newer(new: AnnotationCandidate, old: AnnotationCandidate) -> bool:
    new_ts = _parse_ts(new.annotation_updated_at)
    old_ts = _parse_ts(old.annotation_updated_at)
    if new_ts != old_ts:
        return new_ts > old_ts
    # Deterministic tie-breaker across duplicate exports.
    return str(new.source_json) > str(old.source_json)


def read_eval_videos(path: Path) -> List[EvalVideo]:
    rows: List[EvalVideo] = []
    with Path(path).open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Evaluation CSV has no header: {path}")
        required = {"split", "video_stem", "site", "local_video_path"}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Evaluation CSV missing required columns {sorted(missing)}: {path}"
            )
        for row in reader:
            video_stem = (row.get("video_stem") or "").strip()
            if not video_stem:
                continue
            rows.append(
                EvalVideo(
                    split=(row.get("split") or "").strip(),
                    video_stem=video_stem,
                    site=(row.get("site") or "").strip(),
                    local_video_path=(row.get("local_video_path") or "").strip(),
                )
            )
    if not rows:
        raise RuntimeError(f"No videos found in evaluation CSV: {path}")
    splits = {r.split for r in rows}
    if len(splits) != 1:
        raise ValueError(
            f"Evaluation CSV must contain exactly one split, found {sorted(splits)}"
        )
    return rows


def load_metadata_by_stem(paths: Sequence[Path]) -> Dict[str, Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {}
    for path in paths:
        if not Path(path).exists():
            continue
        with Path(path).open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stem = (row.get("video_stem") or "").strip()
                if stem:
                    merged[stem] = dict(row)
    return merged


def interpolate_track_sequence(seq: Iterable[dict]) -> List[TrackFrame]:
    """
    Expand one Label Studio VideoRectangle sequence using the same semantics as
    the YOLO converter:

    * every keyframe exists at its own frame, regardless of enabled;
    * interpolate strictly between consecutive keyframes only when the starting
      keyframe has enabled=True;
    * a disabled keyframe may still be the end of interpolation from a previous
      enabled keyframe, but it does not interpolate forward.
    """
    kfs = sorted(
        [k for k in seq if isinstance(k, dict)],
        key=lambda k: int(safe_float(k.get("frame"), 0)),
    )
    if not kfs:
        return []

    by_frame: Dict[int, TrackFrame] = {}

    for k in kfs:
        frame_idx = int(safe_float(k.get("frame"), -1))
        if frame_idx < 0:
            continue
        by_frame[frame_idx] = TrackFrame(
            frame_idx=frame_idx,
            x=safe_float(k.get("x")),
            y=safe_float(k.get("y")),
            width=safe_float(k.get("width")),
            height=safe_float(k.get("height")),
            rotation=safe_float(k.get("rotation"), 0.0),
            is_keyframe=True,
            keyframe_enabled=bool(k.get("enabled", True)),
        )

    for idx in range(len(kfs) - 1):
        k0 = kfs[idx]
        k1 = kfs[idx + 1]
        f0 = int(safe_float(k0.get("frame"), -1))
        f1 = int(safe_float(k1.get("frame"), -1))
        if f0 < 0 or f1 <= f0:
            continue
        if not bool(k0.get("enabled", True)):
            continue

        x0 = safe_float(k0.get("x"))
        y0 = safe_float(k0.get("y"))
        w0 = safe_float(k0.get("width"))
        h0 = safe_float(k0.get("height"))
        r0 = safe_float(k0.get("rotation"), 0.0)

        x1 = safe_float(k1.get("x"))
        y1 = safe_float(k1.get("y"))
        w1 = safe_float(k1.get("width"))
        h1 = safe_float(k1.get("height"))
        r1 = safe_float(k1.get("rotation"), 0.0)

        for frame_idx in range(f0 + 1, f1):
            t = (frame_idx - f0) / float(f1 - f0)
            by_frame[frame_idx] = TrackFrame(
                frame_idx=frame_idx,
                x=x0 + (x1 - x0) * t,
                y=y0 + (y1 - y0) * t,
                width=w0 + (w1 - w0) * t,
                height=h0 + (h1 - h0) * t,
                rotation=r0 + (r1 - r0) * t,
                is_keyframe=False,
                keyframe_enabled=None,
            )

    return [by_frame[f] for f in sorted(by_frame)]


def _to_pixel_xywh(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    video_width: int,
    video_height: int,
    forced_mode: str,
) -> Tuple[float, float, float, float]:
    mode = forced_mode
    if mode == "auto":
        mode = infer_coord_mode(x, y, width, height)

    if mode == "percent":
        return (
            x / 100.0 * video_width,
            y / 100.0 * video_height,
            width / 100.0 * video_width,
            height / 100.0 * video_height,
        )
    if mode == "normalized":
        return (
            x * video_width,
            y * video_height,
            width * video_width,
            height * video_height,
        )
    if mode == "pixel":
        return x, y, width, height
    raise ValueError(f"Unknown coord_mode: {forced_mode!r}")


def _video_dimensions(item: Optional[dict], metadata: Dict[str, str]) -> Tuple[int, int]:
    data = (item or {}).get("data") or {}
    width = int(safe_float(data.get("metadata_video_width"), 0))
    height = int(safe_float(data.get("metadata_video_height"), 0))
    if width <= 0:
        width = int(safe_float(metadata.get("width"), 0))
    if height <= 0:
        height = int(safe_float(metadata.get("height"), 0))
    return width, height


def _video_fps(item: Optional[dict], metadata: Dict[str, str]) -> float:
    data = (item or {}).get("data") or {}
    # Prefer already-normalized metadata index values when available.
    fps = safe_float(metadata.get("fps"), 0.0)
    if fps > 0:
        return fps
    duration = safe_float(data.get("metadata_video_duration", data.get("duration")), 0.0)
    nb_frames = int(safe_float(data.get("metadata_video_nb_frames"), 0))
    if duration > 0 and nb_frames > 0:
        return nb_frames / duration
    return 0.0


def _video_nb_frames(item: Optional[dict], metadata: Dict[str, str]) -> int:
    data = (item or {}).get("data") or {}
    nb_frames = int(safe_float(data.get("metadata_video_nb_frames"), 0))
    if nb_frames <= 0:
        nb_frames = int(safe_float(metadata.get("nb_frames"), 0))
    return nb_frames


def _collect_annotation_candidates(
    *,
    eval_videos: Sequence[EvalVideo],
    site_index_dir: Path,
    raw_root_override: Optional[Path],
) -> Dict[str, AnnotationCandidate]:
    wanted = {v.video_stem for v in eval_videos}
    sites = sorted({v.site for v in eval_videos if v.site})

    json_paths: set[Path] = set()
    for site in sites:
        manifest = Path(site_index_dir) / f"{site}.json"
        if not manifest.exists():
            continue
        json_paths.update(
            load_json_paths_from_site_manifest(
                manifest,
                raw_root_override=raw_root_override,
            )
        )

    candidates: Dict[str, AnnotationCandidate] = {}
    for json_path in sorted(json_paths):
        for item in _iter_task_items(json_path):
            stem = _task_video_stem(item)
            if stem not in wanted:
                continue
            data = item.get("data") or {}
            site = str(data.get("metadata_file_site_reference_string") or "")
            annotation = _latest_annotation(item)
            candidate = AnnotationCandidate(
                video_stem=stem,
                site=site,
                item=item,
                annotation=annotation,
                annotation_updated_at=_annotation_timestamp(annotation),
                source_json=json_path,
            )
            old = candidates.get(stem)
            if old is None or _candidate_is_newer(candidate, old):
                candidates[stem] = candidate

    return candidates


def build_tracking_ground_truth(
    *,
    eval_csv: Path,
    site_index_dir: Path,
    data_yaml: Path,
    out_gt_csv: Path,
    out_sequences_csv: Path,
    coord_mode: str = "percent",
    metadata_csv_paths: Sequence[Path] = (),
    negative_metadata_csv_paths: Sequence[Path] = (),
    raw_root_override: Optional[Path] = None,
    allow_missing_annotations: bool = False,
    result_type: str = "videorectangle",
    from_name: Optional[str] = None,
    to_name: Optional[str] = None,
) -> BuildStats:
    if coord_mode not in VALID_COORD_MODES:
        raise ValueError(
            f"coord_mode must be one of {sorted(VALID_COORD_MODES)}, got {coord_mode!r}"
        )

    eval_videos = read_eval_videos(eval_csv)
    class_map = load_class_map_from_yolo_yaml(data_yaml)
    metadata = load_metadata_by_stem(metadata_csv_paths)
    negative_metadata = load_metadata_by_stem(negative_metadata_csv_paths)
    candidates = _collect_annotation_candidates(
        eval_videos=eval_videos,
        site_index_dir=site_index_dir,
        raw_root_override=raw_root_override,
    )

    stats = BuildStats(videos_selected=len(eval_videos))
    gt_rows: List[Dict[str, object]] = []
    sequence_rows: List[Dict[str, object]] = []
    missing_annotations: List[str] = []

    for video in sorted(eval_videos, key=lambda v: (v.site, v.video_stem)):
        candidate = candidates.get(video.video_stem)
        meta = metadata.get(video.video_stem, {})
        neg_meta = negative_metadata.get(video.video_stem, {})
        if not meta and neg_meta:
            meta = neg_meta

        if candidate is None:
            is_negative = video.video_stem in negative_metadata
            status = "condition_negative" if is_negative else "annotation_not_found"
            if is_negative:
                stats.videos_condition_negative += 1
                stats.videos_zero_gt += 1
            else:
                stats.videos_annotation_not_found += 1
                missing_annotations.append(video.video_stem)

            width, height = _video_dimensions(None, meta)
            sequence_rows.append(
                {
                    "split": video.split,
                    "video_stem": video.video_stem,
                    "site": video.site,
                    "status": status,
                    "source_json": "",
                    "annotation_updated_at": "",
                    "width": width,
                    "height": height,
                    "fps": _video_fps(None, meta),
                    "nb_frames": _video_nb_frames(None, meta),
                    "n_tracks": 0,
                    "n_gt_rows": 0,
                    "n_keyframes": 0,
                    "unknown_class_tracks": 0,
                    "synthetic_track_uids": 0,
                    "rotated_rows": 0,
                    "local_video_path": video.local_video_path,
                }
            )
            continue

        item = candidate.item
        annotation = candidate.annotation
        width, height = _video_dimensions(item, meta)
        fps = _video_fps(item, meta)
        nb_frames = _video_nb_frames(item, meta)

        results = []
        if annotation is not None:
            for r in annotation.get("result") or []:
                if not isinstance(r, dict):
                    continue
                if r.get("type") != result_type:
                    continue
                if from_name is not None and r.get("from_name") != from_name:
                    continue
                if to_name is not None and r.get("to_name") != to_name:
                    continue
                results.append(r)

        valid_tracks: List[Tuple[int, dict, str, str]] = []
        unknown_for_video = 0
        synthetic_for_video = 0

        for result_index, r in enumerate(results):
            value = r.get("value") or {}
            labels = value.get("labels") or []
            if not labels:
                continue
            class_name = str(labels[0])
            if class_name not in class_map:
                unknown_for_video += 1
                stats.unknown_class_tracks += 1
                continue
            raw_uid = str(r.get("id") or "").strip()
            if raw_uid:
                track_uid = raw_uid
                uid_source = "label_studio"
            else:
                track_uid = f"synthetic_result_{result_index:06d}"
                uid_source = "synthetic_result_index"
                synthetic_for_video += 1
                stats.synthetic_track_uids += 1
            valid_tracks.append((result_index, r, track_uid, uid_source))

        n_keyframes = 0
        n_rows_before = len(gt_rows)
        rotated_for_video = 0

        # MOT IDs are 1-based and need only be unique within a sequence.
        for track_id, (_, r, track_uid, uid_source) in enumerate(valid_tracks, start=1):
            value = r.get("value") or {}
            class_name = str((value.get("labels") or [""])[0])
            class_id = int(class_map[class_name])
            sequence = value.get("sequence") or []
            frames = interpolate_track_sequence(sequence)
            n_keyframes += sum(1 for fr in frames if fr.is_keyframe)

            seen_frames: set[int] = set()
            for fr in frames:
                if fr.frame_idx in seen_frames:
                    raise ValueError(
                        f"Duplicate frame {fr.frame_idx} for track {track_uid} "
                        f"in {video.video_stem}"
                    )
                seen_frames.add(fr.frame_idx)

                if width <= 0 or height <= 0:
                    raise ValueError(
                        f"Missing video dimensions for {video.video_stem}: "
                        f"width={width} height={height}"
                    )

                x_px, y_px, w_px, h_px = _to_pixel_xywh(
                    x=fr.x,
                    y=fr.y,
                    width=fr.width,
                    height=fr.height,
                    video_width=width,
                    video_height=height,
                    forced_mode=coord_mode,
                )
                xc, yc, wn, hn = to_yolo(
                    fr.x,
                    fr.y,
                    fr.width,
                    fr.height,
                    vid_w=width,
                    vid_h=height,
                    forced_mode=coord_mode,
                )

                if not all(
                    math.isfinite(v)
                    for v in (x_px, y_px, w_px, h_px, xc, yc, wn, hn)
                ):
                    raise ValueError(
                        f"Non-finite GT box for {video.video_stem} track {track_uid} "
                        f"frame {fr.frame_idx}"
                    )

                if abs(fr.rotation) > 1e-9:
                    rotated_for_video += 1
                    stats.rotated_rows += 1

                gt_rows.append(
                    {
                        "split": video.split,
                        "video_stem": video.video_stem,
                        "site": video.site,
                        "frame_idx": fr.frame_idx,
                        "mot_frame": fr.frame_idx + 1,
                        "track_id": track_id,
                        "track_uid": track_uid,
                        "track_uid_source": uid_source,
                        "class_id": class_id,
                        "class_name": class_name,
                        "x_px": x_px,
                        "y_px": y_px,
                        "width_px": w_px,
                        "height_px": h_px,
                        "xc_norm": xc,
                        "yc_norm": yc,
                        "width_norm": wn,
                        "height_norm": hn,
                        "rotation_deg": fr.rotation,
                        "is_keyframe": str(fr.is_keyframe).lower(),
                        "keyframe_enabled": (
                            "" if fr.keyframe_enabled is None
                            else str(fr.keyframe_enabled).lower()
                        ),
                        "source_json": str(candidate.source_json),
                    }
                )

        n_gt_rows = len(gt_rows) - n_rows_before
        n_tracks = len(valid_tracks)
        if n_tracks > 0:
            stats.videos_with_tracks += 1
            stats.tracks_written += n_tracks
        else:
            stats.videos_zero_gt += 1

        sequence_rows.append(
            {
                "split": video.split,
                "video_stem": video.video_stem,
                "site": video.site,
                "status": "ok" if n_tracks > 0 else "no_tracks",
                "source_json": str(candidate.source_json),
                "annotation_updated_at": candidate.annotation_updated_at,
                "width": width,
                "height": height,
                "fps": fps,
                "nb_frames": nb_frames,
                "n_tracks": n_tracks,
                "n_gt_rows": n_gt_rows,
                "n_keyframes": n_keyframes,
                "unknown_class_tracks": unknown_for_video,
                "synthetic_track_uids": synthetic_for_video,
                "rotated_rows": rotated_for_video,
                "local_video_path": video.local_video_path,
            }
        )

    gt_rows.sort(
        key=lambda r: (
            str(r["video_stem"]),
            int(r["mot_frame"]),
            int(r["track_id"]),
        )
    )
    sequence_rows.sort(key=lambda r: (str(r["site"]), str(r["video_stem"])))

    out_gt_csv = Path(out_gt_csv)
    out_sequences_csv = Path(out_sequences_csv)
    out_gt_csv.parent.mkdir(parents=True, exist_ok=True)
    out_sequences_csv.parent.mkdir(parents=True, exist_ok=True)

    gt_fieldnames = [
        "split",
        "video_stem",
        "site",
        "frame_idx",
        "mot_frame",
        "track_id",
        "track_uid",
        "track_uid_source",
        "class_id",
        "class_name",
        "x_px",
        "y_px",
        "width_px",
        "height_px",
        "xc_norm",
        "yc_norm",
        "width_norm",
        "height_norm",
        "rotation_deg",
        "is_keyframe",
        "keyframe_enabled",
        "source_json",
    ]
    with out_gt_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=gt_fieldnames)
        writer.writeheader()
        writer.writerows(gt_rows)

    sequence_fieldnames = [
        "split",
        "video_stem",
        "site",
        "status",
        "source_json",
        "annotation_updated_at",
        "width",
        "height",
        "fps",
        "nb_frames",
        "n_tracks",
        "n_gt_rows",
        "n_keyframes",
        "unknown_class_tracks",
        "synthetic_track_uids",
        "rotated_rows",
        "local_video_path",
    ]
    with out_sequences_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sequence_fieldnames)
        writer.writeheader()
        writer.writerows(sequence_rows)

    stats.gt_rows_written = len(gt_rows)

    if missing_annotations and not allow_missing_annotations:
        preview = "\n".join(f"  - {stem}" for stem in missing_annotations[:20])
        raise RuntimeError(
            f"Tracking GT annotation not found for {len(missing_annotations)} "
            f"selected video(s). Outputs were written for diagnostics.\n{preview}"
        )

    return stats


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build canonical per-frame tracking ground truth for a val/test video "
            "index from original Label Studio VideoRectangle annotations."
        )
    )
    p.add_argument("--eval-csv", required=True, type=Path)
    p.add_argument("--site-index-dir", required=True, type=Path)
    p.add_argument("--data-yaml", required=True, type=Path)
    p.add_argument("--out-gt-csv", required=True, type=Path)
    p.add_argument("--out-sequences-csv", required=True, type=Path)
    p.add_argument(
        "--metadata-csv",
        nargs="*",
        type=Path,
        default=[],
        help="Optional metadata CSVs used for dimensions/fps fallbacks.",
    )
    p.add_argument(
        "--negative-metadata-csv",
        nargs="*",
        type=Path,
        default=[],
        help=(
            "Metadata CSVs whose stems are known zero-GT condition-negative videos."
        ),
    )
    p.add_argument(
        "--manifest-raw-root",
        type=Path,
        default=None,
        help="Optional raw_root override for the site-index manifests.",
    )
    p.add_argument(
        "--coord-mode",
        choices=sorted(VALID_COORD_MODES),
        default="percent",
    )
    p.add_argument("--from-name", default=None)
    p.add_argument("--to-name", default=None)
    p.add_argument(
        "--allow-missing-annotations",
        action="store_true",
        help=(
            "Write annotation_not_found sequence rows without failing the stage. "
            "Known condition negatives are always allowed."
        ),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    stats = build_tracking_ground_truth(
        eval_csv=args.eval_csv,
        site_index_dir=args.site_index_dir,
        data_yaml=args.data_yaml,
        out_gt_csv=args.out_gt_csv,
        out_sequences_csv=args.out_sequences_csv,
        coord_mode=args.coord_mode,
        metadata_csv_paths=args.metadata_csv,
        negative_metadata_csv_paths=args.negative_metadata_csv,
        raw_root_override=args.manifest_raw_root,
        allow_missing_annotations=args.allow_missing_annotations,
        from_name=args.from_name,
        to_name=args.to_name,
    )
    print(
        "Tracking GT built: "
        f"videos_selected={stats.videos_selected} "
        f"videos_with_tracks={stats.videos_with_tracks} "
        f"videos_zero_gt={stats.videos_zero_gt} "
        f"videos_condition_negative={stats.videos_condition_negative} "
        f"videos_annotation_not_found={stats.videos_annotation_not_found} "
        f"tracks_written={stats.tracks_written} "
        f"gt_rows_written={stats.gt_rows_written} "
        f"synthetic_track_uids={stats.synthetic_track_uids} "
        f"unknown_class_tracks={stats.unknown_class_tracks} "
        f"rotated_rows={stats.rotated_rows}"
    )


if __name__ == "__main__":
    main()
