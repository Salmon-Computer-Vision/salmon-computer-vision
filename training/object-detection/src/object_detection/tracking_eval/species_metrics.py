"""Class-aware MOT metrics, preserving original species IDs from canonical data.

Stock TrackEval MotChallenge2DBox supports only class 1 (pedestrian). For each
species we select its GT and predicted boxes, map those boxes to MOT class 1,
and evaluate independently. Predicted classes are *per frame*, so classification
instability causes missed GT rows and incorrect-species false positives.

GT CSV is partitioned in one streaming pass instead of loaded all at once.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .eval_common import exact_int, write_csv
from .tracking_metrics import make_mot_workspace, trackeval_metrics


SCORE_FIELDS = ["HOTA", "DetA", "AssA", "MOTA", "MOTP", "FP", "FN", "TP",
                "IDSW", "IDF1", "IDP", "IDR"]
SPECIES_COLUMNS = ["split", "class_id", "class_name", "status", "gt_detections",
                   "pred_detections", "gt_sequences", "pred_sequences",
                   "evaluated_sequences", *SCORE_FIELDS]


def partition_gt_by_species(gt_csv: Path, selected: dict, names: dict[int, str],
                            out_dir: Path, split: str):
    """Write one CSV per species, return per-sequence counts + distinct tracks.

    Validation of GT row geometry and time bounds remains the responsibility of
    the shared MOT materializer (called below), not this partitioner.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = defaultdict(lambda: defaultdict(int))
    tracks = defaultdict(lambda: defaultdict(set))
    rotated = defaultdict(lambda: defaultdict(int))
    with Path(gt_csv).open(newline="", encoding="utf-8") as fh, ExitStack() as stack:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        required = {"split", "video_stem", "class_id", "track_id", "rotation_deg"}
        if not required <= set(fields):
            raise ValueError(f"GT CSV missing columns: {sorted(required-set(fields))}")
        writers = {}
        for cls in names:
            handle = stack.enter_context((out_dir / f"species_{cls}.csv").open("w", newline="", encoding="utf-8"))
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writers[cls] = writer
        for row in reader:
            stem = row["video_stem"]
            if row["split"] != split:
                raise ValueError(f"GT row split differs from {split}: {stem}")
            if stem not in selected:
                continue
            cls = exact_int(row["class_id"], "class_id")
            if cls not in names:
                raise ValueError(f"Unknown GT class id {cls} in {stem}")
            writers[cls].writerow(row)
            counts[cls][stem] += 1
            tracks[cls][stem].add(exact_int(row["track_id"], "track_id"))
            if float(row.get("rotation_deg") or 0) != 0:
                rotated[cls][stem] += 1
    return counts, tracks, rotated


def species_sequence_info(selected: dict, gt_counts: dict, gt_tracks: dict,
                          rotated_counts: dict, pred_counts: dict):
    """Keep all sequences containing a GT or prediction of this species.

    Critically this includes prediction-only clips, so incorrect species
    predictions in fully reviewed negative videos are scored as FPs.
    """
    active = {}
    for stem, seq in selected.items():
        gt_n = gt_counts.get(stem, 0)
        p_n = pred_counts.get(stem, 0)
        if not (gt_n or p_n):
            continue
        s = dict(seq)
        s.update(n_gt_rows=gt_n, n_tracks=len(gt_tracks.get(stem, set())),
                 rotated_rows=rotated_counts.get(stem, 0),
                 status="ok" if gt_n else "no_tracks")
        active[stem] = s
    return active


def evaluate_species_tracking(*, gt_csv: Path, selected: dict, predictions: dict,
                              names: dict[int, str], split: str, benchmark: str,
                              tracker: str, temp_path: Path, backend: Any = None) -> list[dict]:
    temp_path.mkdir(parents=True, exist_ok=True)
    counts, tracks, rotated = partition_gt_by_species(gt_csv, selected, names,
                                                       temp_path / "partition", split)
    by_class = defaultdict(lambda: defaultdict(list))
    pred_counts = defaultdict(lambda: defaultdict(int))
    for stem, rows in predictions.items():
        for row in rows:
            cls = exact_int(row["class_id"], "class_id")
            if cls not in names:
                raise ValueError(f"Unknown prediction class id {cls} in {stem}")
            by_class[cls][stem].append(row)
            pred_counts[cls][stem] += 1
    output = []
    for cls, name in sorted(names.items()):
        gc = counts[cls]
        pc = pred_counts[cls]
        row = dict(split=split, class_id=cls, class_name=name,
                   gt_detections=sum(gc.values()), pred_detections=sum(pc.values()),
                   gt_sequences=len(gc), pred_sequences=len(pc))
        active = species_sequence_info(selected, gc, tracks[cls], rotated[cls], pc)
        row["evaluated_sequences"] = len(active)
        if row["gt_detections"] == 0:
            # HOTA/IDF1 aren't meaningful with no GT of this species.
            # Preserve FP counts from predictions as an explicit diagnostic.
            row.update(status="no_gt", **{m: None for m in SCORE_FIELDS})
            row.update(FP=row["pred_detections"], FN=0, TP=0, IDSW=0)
        else:
            workspace = temp_path / f"run_{cls}"
            workspace.mkdir()
            subset = {stem: by_class[cls].get(stem, []) for stem in active}
            gt_root, tracker_root = make_mot_workspace(
                directory=workspace, gt_csv=temp_path / "partition" / f"species_{cls}.csv",
                sequence_csv=_write_species_sequences(workspace / "sequences.csv", active),
                split=split, benchmark=benchmark, tracker=tracker,
                selected=active, predictions=subset)
            _, metrics = trackeval_metrics(
                gt_root=gt_root, tracker_root=tracker_root,
                output_root=workspace / "scores", benchmark=benchmark, split=split,
                tracker=tracker, selected=active, trackeval_module=backend)
            row.update(status="scored", **metrics)
            # Workspace is ephemeral, no need to retain files until next class.
            import shutil
            shutil.rmtree(workspace)
        output.append(row)
    return output


def _write_species_sequences(path: Path, active: dict) -> Path:
    required = ["split", "video_stem", "status", "width", "height", "fps",
                "nb_frames", "n_tracks", "n_gt_rows", "rotated_rows"]
    rows = [{key: info.get(key, "") for key in required} for stem, info in active.items()]
    # Sequence source often includes site. The materializer doesn't require it.
    write_csv(path, rows, required)
    return path
