"""Directional salmon counts from the same canonical detections used by TrackEval.

Implements the offline, deterministic core of the provided SalmonCounter:
 - per-track first/last *eligible center-x* vs vertical half-width line
 - right counts l->r, left counts r->l (r_/l_ prefixes)
 - vote_method all/confidence/ignore_thin
 - drop_bounding_boxes means y-center > int(height * bound_line_ratio)
 - gap longer than tracking_thresh absent frames finalizes a segment

This is NOT a bit-for-bit replay of deployment scheduling/cleanup. In particular
we include the last decoded observation at end-of-video rather than inheriting
its legacy last-frame ordering bug.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .eval_common import (
    as_bool, csv_rows, exact_int, finite_float, predictions_by_video, select_sequences,
    write_csv, write_json,
)


def load_class_names(path: Path) -> dict[int, str]:
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    names = data.get("names") if isinstance(data, dict) else None
    if isinstance(names, list):
        out = {i: str(name) for i, name in enumerate(names)}
    elif isinstance(names, dict):
        out = {int(i): str(name) for i, name in names.items()}
    else:
        raise ValueError(f"Expected names list/dictionary in {path}")
    if not out or len(set(out.values())) != len(out):
        raise ValueError(f"Empty or duplicate class names in {path}")
    return out


@dataclass(frozen=True)
class CountSettings:
    tracking_thresh: int = 10
    vote_method: str = "all"
    drop_bounding_boxes: bool = False
    bound_line_ratio: float = 0.5

    def validate(self):
        if self.tracking_thresh < 0:
            raise ValueError("tracking_thresh must be >= 0")
        if self.vote_method not in {"all", "confidence", "ignore_thin"}:
            raise ValueError("Unknown vote_method")
        if not 0.0 <= self.bound_line_ratio <= 1.0:
            raise ValueError("bound_line_ratio must be in [0,1]")


def _center(row: dict, *, ground_truth: bool) -> tuple[float, float]:
    x = finite_float(row["x_px"], "x_px")
    y = finite_float(row["y_px"], "y_px")
    w = finite_float(row["width_px"], "width_px")
    h = finite_float(row["height_px"], "height_px")
    if w <= 0 or h <= 0:
        raise ValueError("Nonpositive box area")
    if ground_truth:
        theta = math.radians(finite_float(row.get("rotation_deg", 0), "rotation_deg"))
        return (x + w/2*math.cos(theta) - h/2*math.sin(theta),
                y + w/2*math.sin(theta) + h/2*math.cos(theta))
    return x+w/2, y+h/2


def count_track_events(rows: list[dict], *, frame_width: int, frame_height: int,
                       settings: CountSettings, ground_truth: bool) -> list[dict]:
    """One event for each finished track segment crossing the vertical midline."""
    settings.validate()
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        tid = exact_int(row["track_id"], "track_id")
        f = exact_int(row["frame_idx"], "frame_idx")
        if tid < 1 or f < 0:
            raise ValueError(f"Bad track or frame id: {tid}/{f}")
        groups[tid].append(row)
    events = []
    boundary = frame_width / 2
    roi_end = int(frame_height * settings.bound_line_ratio)

    def finish(segment: list[dict], tid: int, part: int):
        points = []
        votes: dict[int, float] = {}
        for r in segment:
            x, y = _center(r, ground_truth=ground_truth)
            w, h = float(r["width_px"]), float(r["height_px"])
            if not settings.drop_bounding_boxes or y <= roi_end:
                points.append((int(r["frame_idx"]), x))
            # Deployment votes on all tracked boxes, even if the ROI excludes
            # a point from the trajectory (see salmon_counter.py).
            if settings.vote_method != "ignore_thin" or w > h:
                cls = exact_int(r["class_id"], "class_id")
                weight = (finite_float(r["confidence"], "confidence") if settings.vote_method == "confidence" and not ground_truth else 1.0)
                votes[cls] = votes.get(cls, 0.0) + weight
        if len(points) < 2 or not votes:
            return
        # Dict insertion order preserves first-seen class for tied votes.
        species = max(votes, key=votes.get)
        first, last = points[0][1], points[-1][1]
        direction = None
        if first < boundary and last >= boundary:
            direction = "r"  # move to the right (r_ prefix)
        elif first > boundary and last <= boundary:
            direction = "l"  # move to the left (l_ prefix)
        if direction:
            events.append({"track_id": tid, "segment": part, "class_id": species,
                           "direction": direction, "start_frame": points[0][0],
                           "end_frame": points[-1][0]})

    for tid, group in sorted(groups.items()):
        group.sort(key=lambda r: int(r["frame_idx"]))
        if any(int(b["frame_idx"]) == int(a["frame_idx"]) for a, b in zip(group, group[1:])):
            raise ValueError(f"Duplicate frame within track {tid}")
        segment: list[dict] = []
        part = 0
        for row in group:
            # Deployment's track count is decremented once per missed frame;
            # expiration occurs after > tracking_thresh missed frames.
            if segment and (int(row["frame_idx"]) - int(segment[-1]["frame_idx"]) - 1) > settings.tracking_thresh:
                finish(segment, tid, part)
                segment = []
                part += 1
            segment.append(row)
        if segment:
            finish(segment, tid, part)
    return events


def load_gt_tracks(gt_csv: Path, selected: dict[str, dict[str, str]], split: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    required = {"split", "video_stem", "frame_idx", "mot_frame", "track_id", "class_id", "x_px", "y_px", "width_px", "height_px", "rotation_deg"}
    with Path(gt_csv).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f"GT CSV missing {sorted(required-set(reader.fieldnames or ())) }")
        for r in reader:
            stem = r["video_stem"]
            if r["split"] != split:
                raise ValueError(f"GT split mismatch for {stem}")
            if stem not in selected:
                continue
            fidx = exact_int(r["frame_idx"], "frame_idx")
            motidx = exact_int(r["mot_frame"], "mot_frame")
            tid = exact_int(r["track_id"], "track_id")
            if tid < 1 or fidx < 0 or fidx >= int(selected[stem]["nb_frames"]) or motidx != fidx+1:
                raise ValueError(f"GT row frame/index invalid in {stem}: {fidx}")
            key = (stem, fidx, tid)
            if key in seen:
                raise ValueError(f"Duplicate GT track frame {key}")
            seen.add(key)
            for c in ("class_id", "x_px", "y_px", "width_px", "height_px", "rotation_deg"):
                (exact_int if c == "class_id" else finite_float)(r[c], c)
            _center(r, ground_truth=True)
            out[stem].append(r)
    for stem, seq in selected.items():
        if len(out.get(stem, [])) != int(seq["n_gt_rows"]):
            raise ValueError(f"GT row count mismatch for {stem}")
    return out


def aggregate_counts(events: list[dict], selected: dict, names: dict[int, str], split: str):
    """Output sparse per video/class/direction comparisons plus complete video totals."""
    groups: dict[tuple[str, int, str], dict[str, int]] = defaultdict(lambda: {"gt_count": 0, "pred_count": 0})
    for event in events:
        key = (event["video_stem"], int(event["class_id"]), event["direction"])
        groups[key]["gt_count" if event["source"] == "gt" else "pred_count"] += 1
    detail = []
    for (stem, cls, direction), counts in sorted(groups.items()):
        g, p = counts["gt_count"], counts["pred_count"]
        detail.append({"split": split, "site": selected[stem].get("site", ""),
                       "video_stem": stem, "class_id": cls,
                       "class_name": names.get(cls, f"UNKNOWN_CLASS_{cls}"),
                       "direction": direction, "gt_count": g, "pred_count": p,
                       "signed_error": p-g, "absolute_error": abs(p-g)})
    totals: dict[str, dict[str, int]] = {stem: {"gt_count": 0, "pred_count": 0} for stem in selected}
    for row in detail:
        totals[row["video_stem"]]["gt_count"] += row["gt_count"]
        totals[row["video_stem"]]["pred_count"] += row["pred_count"]
    by_video = []
    for stem, counts in sorted(totals.items()):
        g, p = counts["gt_count"], counts["pred_count"]
        by_video.append({"split": split, "site": selected[stem].get("site", ""),
                         "video_stem": stem, "gt_count": g, "pred_count": p,
                         "signed_error": p-g, "absolute_error": abs(p-g)})
    return detail, by_video



def aggregate_site_direction(detail: list[dict], selected: dict[str, dict[str, str]], split: str) -> list[dict]:
    """Aggregate per-site/species/direction with GT-normalized absolute error.

    The denominator of MAE is the number of evaluated videos at that site,
    including those with zero events (avoids selection-biased MAE).
    """
    site_n = Counter(seq.get("site", "") for seq in selected.values())
    groups = defaultdict(lambda: {"gt_count": 0, "pred_count": 0, "absolute_error_sum": 0})
    for item in detail:
        key = (item["site"], item["class_id"], item["class_name"], item["direction"])
        out = groups[key]
        out["gt_count"] += item["gt_count"]
        out["pred_count"] += item["pred_count"]
        out["absolute_error_sum"] += item["absolute_error"]
    output = []
    for (site, cls, name, direction), rec in sorted(groups.items()):
        g, p, err = rec["gt_count"], rec["pred_count"], rec["absolute_error_sum"]
        output.append({"split": split, "site": site, "class_id": cls, "class_name": name,
                       "direction": direction, "num_videos": site_n[site],
                       "gt_count": g, "pred_count": p, "signed_error": p - g,
                       "absolute_error_sum": err, "MAE_per_video": err/site_n[site],
                       "nMAE": err/g if g else None})
    return output


def aggregate_species_directional(detail: list[dict], selected: dict,
                                  names: dict[int, str], split: str) -> list[dict]:
    """Species totals and errors summed across (video, direction).

    Sum absolute differences BEFORE aggregation; never cancel opposing
    directions or errors from different videos. MAE denominator includes all
    successfully evaluated videos, even those with zero fish.
    """
    totals = {cls: dict(gt_count=0, pred_count=0, absolute_error_sum=0)
              for cls in names}
    for row in detail:
        cls = int(row["class_id"])
        if cls not in totals:
            raise ValueError(f"Unknown counted species id {cls}")
        totals[cls]["gt_count"] += int(row["gt_count"])
        totals[cls]["pred_count"] += int(row["pred_count"])
        totals[cls]["absolute_error_sum"] += int(row["absolute_error"])
    n = len(selected)
    if not n:
        raise ValueError("No evaluated videos")
    result = []
    for cls, name in sorted(names.items()):
        values = totals[cls]
        gt, pred, error = values["gt_count"], values["pred_count"], values["absolute_error_sum"]
        result.append(dict(split=split, class_id=cls, class_name=name,
                           num_videos=n, gt_count=gt, pred_count=pred,
                           signed_error=pred-gt, absolute_error_sum=error,
                           MAE_per_video=error/n,
                           nMAE=error/gt if gt else None))
    return result


def evaluate_counts(*, gt_csv: Path, sequence_csv: Path, inference_status_csv: Path,
                    predictions_parquet: Path, data_yaml: Path, split: str,
                    settings: CountSettings, scope: str,
                    summary_json: Path, per_group_csv: Path, per_video_csv: Path,
                    per_site_csv: Path,
                    events_csv: Path, coverage_csv_out: Path,
                    coverage_csv: Path | None = None,
                    per_species_csv: Path | None = None) -> dict:
    selected, ledger = select_sequences(sequence_csv=sequence_csv, inference_status_csv=inference_status_csv,
                                        split=split, scope=scope, coverage_csv=coverage_csv)
    if not selected:
        raise ValueError(f"No eligible sequences for counting {split}")
    names = load_class_names(data_yaml)
    preds = predictions_by_video(predictions_parquet, split=split, selected=selected,
                                 inference_status_csv=inference_status_csv)
    gt = load_gt_tracks(gt_csv, selected, split)
    all_events: list[dict] = []
    for stem, seq in selected.items():
        for source, rows in (("gt", gt.get(stem, [])), ("pred", preds.get(stem, []))):
            for event in count_track_events(rows, frame_width=int(seq["width"]), frame_height=int(seq["height"]),
                                           settings=settings, ground_truth=(source == "gt")):
                all_events.append({"split": split, "video_stem": stem,
                                   "site": seq.get("site", ""), "source": source,
                                   "class_name": names.get(event["class_id"], f"UNKNOWN_CLASS_{event['class_id']}"),
                                   **event})
    detail, videos = aggregate_counts(all_events, selected, names, split)
    by_site = aggregate_site_direction(detail, selected, split)
    by_species = aggregate_species_directional(detail, selected, names, split)
    abs_err = sum(x["absolute_error"] for x in detail)
    gt_total = sum(x["gt_count"] for x in detail)
    pred_total = sum(x["pred_count"] for x in detail)
    # Note: overall absolute error sums over (video, species, direction),
    # which reveals mutually cancelling misclassifications/directions.
    summary = {
        "split": split, "annotation_scope": scope,
        "annotation_coverage_verified": scope == "verified",
        "interpretation": ("reviewed fully annotated sequences" if scope == "verified" else
                           "PROVISIONAL: nonempty Label Studio GT does not prove complete fish annotation"),
        "settings": vars(settings), "sequences_selected": len(ledger),
        "sequences_evaluated": len(selected),
        "exclusions": dict(Counter(x["reason"] for x in ledger if x["reason"])),
        "gt_events": gt_total, "pred_events": pred_total,
        "absolute_error_sum_class_direction": abs_err,
        "nMAE_class_direction": abs_err / gt_total if gt_total else None,
        "MAE_per_video_class_direction": abs_err / len(selected),
        "MAE_video_total": sum(x["absolute_error"] for x in videos) / len(selected),
        "signed_bias_total": pred_total - gt_total,
    }
    write_csv(per_group_csv, detail, ["split", "site", "video_stem", "class_id", "class_name", "direction",
                                      "gt_count", "pred_count", "signed_error", "absolute_error"])
    write_csv(per_video_csv, videos, ["split", "site", "video_stem", "gt_count", "pred_count", "signed_error", "absolute_error"])
    write_csv(per_site_csv, by_site, ["split", "site", "class_id", "class_name", "direction", "num_videos",
                                     "gt_count", "pred_count", "signed_error", "absolute_error_sum", "MAE_per_video", "nMAE"])
    if per_species_csv is not None:
        write_csv(per_species_csv, by_species,
                  ["split", "class_id", "class_name", "num_videos", "gt_count",
                   "pred_count", "signed_error", "absolute_error_sum",
                   "MAE_per_video", "nMAE"])
    write_csv(events_csv, all_events, ["split", "video_stem", "site", "source", "class_name", "track_id", "segment", "class_id", "direction", "start_frame", "end_frame"])
    write_csv(coverage_csv_out, ledger, ["split", "video_stem", "site", "n_gt_rows", "status", "reason", "annotation_verified"])
    write_json(summary_json, summary)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description="SalmonCounter-aligned directional counting metrics")
    p.add_argument("--gt-csv", type=Path, required=True)
    p.add_argument("--sequences-csv", type=Path, required=True)
    p.add_argument("--inference-status-csv", type=Path, required=True)
    p.add_argument("--predictions-parquet", type=Path, required=True)
    p.add_argument("--data-yaml", type=Path, required=True)
    p.add_argument("--split", choices=["val", "test"], required=True)
    p.add_argument("--tracking-thresh", type=int, default=10)
    p.add_argument("--vote-method", choices=["all", "confidence", "ignore_thin"], default="all")
    p.add_argument("--drop-bounding-boxes", type=as_bool, default=False,
                   help="Boolean value (true/false); matches deployment flag")
    p.add_argument("--bound-line-ratio", type=float, default=0.5)
    p.add_argument("--annotation-scope", choices=["observed", "verified"], default="observed")
    p.add_argument("--coverage-csv", type=Path)
    p.add_argument("--summary-json", type=Path, required=True)
    p.add_argument("--per-group-csv", type=Path, required=True)
    p.add_argument("--per-video-csv", type=Path, required=True)
    p.add_argument("--per-site-csv", type=Path, required=True)
    p.add_argument("--per-species-csv", type=Path)
    p.add_argument("--events-csv", type=Path, required=True)
    p.add_argument("--coverage-output-csv", type=Path, required=True)
    a = p.parse_args(argv)
    result = evaluate_counts(gt_csv=a.gt_csv, sequence_csv=a.sequences_csv,
        inference_status_csv=a.inference_status_csv, predictions_parquet=a.predictions_parquet,
        data_yaml=a.data_yaml, split=a.split,
        settings=CountSettings(a.tracking_thresh, a.vote_method, a.drop_bounding_boxes, a.bound_line_ratio),
        scope=a.annotation_scope, coverage_csv=a.coverage_csv,
        summary_json=a.summary_json, per_group_csv=a.per_group_csv, per_video_csv=a.per_video_csv,
        per_site_csv=a.per_site_csv, per_species_csv=a.per_species_csv,
        events_csv=a.events_csv, coverage_csv_out=a.coverage_output_csv)
    print(f"Counting {a.split}: {result}")


if __name__ == "__main__":
    main()
