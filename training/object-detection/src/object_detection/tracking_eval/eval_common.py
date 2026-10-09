"""Shared evaluation selection and strict schema checks for SalmonVision tracking.

Only successfully decoded videos with exact frame-count agreement are scored.
`observed` is exploratory, NOT verified full-annotation coverage: zero-GT
sequences are excluded, while other videos may still be incompletely labeled.
`verified` requires an independently curated coverage CSV.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def csv_rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        absent = required - set(reader.fieldnames or [])
        if absent:
            raise ValueError(f"{path}: missing columns {sorted(absent)}")
        return list(reader)


def keyed(rows: list[dict[str, str]], split: str, label: str) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        stem = (row.get("video_stem") or "").strip()
        if not stem or stem in {".", ".."} or Path(stem).name != stem or any(c in stem for c in ("/", "\\")):
            raise ValueError(f"{label}: unsafe sequence name {stem!r}")
        if row.get("split") != split:
            raise ValueError(f"{label}: split mismatch for {stem}")
        if stem in result:
            raise ValueError(f"{label}: duplicate sequence {stem}")
        result[stem] = row
    return result


def exact_int(value: Any, label: str) -> int:
    try:
        x = float(value)
        if math.isfinite(x) and x.is_integer():
            return int(x)
    except (TypeError, ValueError):
        pass
    raise ValueError(f"invalid integer {label}={value!r}")


def finite_float(value: Any, label: str) -> float:
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except (TypeError, ValueError):
        pass
    raise ValueError(f"invalid number {label}={value!r}")


def as_bool(value: Any) -> bool:
    if value is True or str(value).lower().strip() in {"true", "1", "yes"}:
        return True
    if value is False or str(value).lower().strip() in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"Invalid boolean: {value!r}")


def select_sequences(*, sequence_csv: Path, inference_status_csv: Path,
                     split: str, scope: str = "observed", coverage_csv: Path | None = None):
    """Returns (selected sequence rows, per-sequence selection ledger).

    scope='observed': nonempty GT in fully decoded videos, exploratory only.
    scope='verified': only fully_annotated=true in user-reviewed coverage CSV;
       verified true negative (0 GT) is included.
    """
    if scope not in {"observed", "verified"}:
        raise ValueError("annotation scope must be observed or verified")
    if scope == "verified" and coverage_csv is None:
        raise ValueError("verified annotation scope requires --coverage-csv")
    seqs = keyed(csv_rows(sequence_csv, {"split", "video_stem", "nb_frames", "n_gt_rows", "width", "height", "status"}), split, "sequences")
    runs = keyed(csv_rows(inference_status_csv, {"split", "video_stem", "status", "eligible_for_evaluation", "frames_decoded", "predictions_written"}), split, "inference")
    if set(seqs) != set(runs):
        raise ValueError(f"Sequence/status video sets differ: missing={sorted(set(seqs)-set(runs))[:5]}, extra={sorted(set(runs)-set(seqs))[:5]}")
    reviewed: dict[str, bool] = {}
    if coverage_csv is not None:
        content = csv_rows(coverage_csv, {"video_stem", "fully_annotated"})
        for row in content:
            stem = row["video_stem"].strip()
            if stem in reviewed:
                raise ValueError(f"Duplicate coverage row for {stem}")
            reviewed[stem] = as_bool(row["fully_annotated"])
        if not set(reviewed) <= set(seqs):
            raise ValueError(f"Coverage CSV has unknown videos: {sorted(set(reviewed)-set(seqs))[:5]}")
    selection, ledger = {}, []
    for stem in sorted(seqs):
        seq, run = seqs[stem], runs[stem]
        nframes = exact_int(seq["nb_frames"], "nb_frames")
        n_gt = exact_int(seq["n_gt_rows"], "n_gt_rows")
        w = exact_int(seq["width"], "width")
        h = exact_int(seq["height"], "height")
        if nframes <= 0 or w <= 0 or h <= 0 or n_gt < 0:
            raise ValueError(f"Bad sequence metadata for {stem}")
        reason = ""
        if run["status"] != "ok" or not as_bool(run["eligible_for_evaluation"]):
            reason = "inference_not_ok"
        elif exact_int(run["frames_decoded"], "frames_decoded") != nframes:
            reason = "decoded_frame_count_mismatch"
        elif seq["status"] not in {"ok", "no_tracks", "condition_negative"}:
            reason = "gt_unavailable"
        elif scope == "observed" and n_gt == 0:
            reason = "no_gt_coverage_unverified"
        elif scope == "verified" and not reviewed.get(stem, False):
            reason = "not_verified_fully_annotated"
        if not reason:
            selection[stem] = seq
        ledger.append({"split": split, "video_stem": stem, "site": seq.get("site", ""),
                       "n_gt_rows": n_gt, "status": "included" if not reason else "excluded",
                       "reason": reason, "annotation_verified": reviewed.get(stem, False)})
    return selection, ledger


def iter_parquet_predictions(path: Path, batch_size: int = 32768):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Please install pyarrow: uv add 'pyarrow>=16'") from exc
    required = {"split", "video_stem", "frame_idx", "mot_frame", "track_id", "class_id", "confidence", "x_px", "y_px", "width_px", "height_px"}
    pf = pq.ParquetFile(path)
    if not required <= set(pf.schema_arrow.names):
        raise ValueError(f"Prediction Parquet missing {sorted(required-set(pf.schema_arrow.names))}")
    for batch in pf.iter_batches(batch_size=batch_size):
        columns = batch.to_pydict()
        for i in range(batch.num_rows):
            yield {name: values[i] for name, values in columns.items()}


def predictions_by_video(path: Path, *, split: str, selected: dict[str, dict[str, str]],
                         inference_status_csv: Path):
    """Strictly validate selected predictions and status row counts."""
    status = keyed(csv_rows(inference_status_csv, {"split", "video_stem", "predictions_written"}), split, "inference")
    out = defaultdict(list)
    seen = set()
    for row in iter_parquet_predictions(path):
        stem = str(row["video_stem"])
        if str(row["split"]) != split:
            raise ValueError(f"Prediction split mismatch: {stem}")
        if stem not in status:
            raise ValueError(f"Prediction for video absent from inference status: {stem}")
        if stem not in selected:
            continue
        frame_idx = exact_int(row["frame_idx"], "frame_idx")
        mot_frame = exact_int(row["mot_frame"], "mot_frame")
        tid = exact_int(row["track_id"], "track_id")
        cls = exact_int(row["class_id"], "class_id")
        if mot_frame != frame_idx+1 or frame_idx < 0 or mot_frame > exact_int(selected[stem]["nb_frames"], "nb_frames"):
            raise ValueError(f"Invalid frame index for {stem}: {frame_idx}/{mot_frame}")
        if tid < 1 or cls < 0:
            raise ValueError(f"Invalid tracker ID or class for {stem}: {tid}/{cls}")
        confidence = finite_float(row["confidence"], "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError(f"Confidence out of range for {stem}: {confidence}")
        for name in ("x_px", "y_px", "width_px", "height_px"):
            finite_float(row[name], name)
        if row["width_px"] <= 0 or row["height_px"] <= 0:
            raise ValueError(f"Nonpositive prediction bbox for {stem}")
        key = stem, frame_idx, tid
        if key in seen:
            raise ValueError(f"Duplicate (video,frame,track_id): {key}")
        seen.add(key)
        out[stem].append(row)
    for stem, rows in out.items():
        expected = exact_int(status[stem]["predictions_written"], "predictions_written")
        if len(rows) != expected:
            raise ValueError(f"Prediction/status row count mismatch for {stem}: {len(rows)} vs {expected}")
        rows.sort(key=lambda r: (r["mot_frame"], r["track_id"]))
    for stem in selected:
        if stem not in out and exact_int(status[stem]["predictions_written"], "predictions_written") != 0:
            raise ValueError(f"Missing prediction rows for {stem}")
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
