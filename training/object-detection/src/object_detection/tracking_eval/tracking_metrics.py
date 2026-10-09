"""TrackEval HOTA/CLEAR/Identity scoring from canonical SalmonVision CSV + Parquet.

All MOT files live in a unique TemporaryDirectory and never enter DVC outs.
"""
from __future__ import annotations

import argparse
import csv
import math
import tempfile
from pathlib import Path
from typing import Any

from .eval_common import (
    csv_rows, finite_float, predictions_by_video, select_sequences,
    write_csv, write_json,
)


def format_tracker_mot_row(row: dict, *, width: int, height: int) -> str:
    """10-column MOT tracker record, class=1 for TrackEval's fish-as-pedestrian mapping.

    Canonical coords are 0-based; clip to visible ROI and add 1 to origin.
    """
    from .eval_common import exact_int
    frame = exact_int(row["mot_frame"], "mot_frame")
    tid = exact_int(row["track_id"], "track_id")
    x = finite_float(row["x_px"], "x_px")
    y = finite_float(row["y_px"], "y_px")
    w = finite_float(row["width_px"], "width_px")
    h = finite_float(row["height_px"], "height_px")
    conf = finite_float(row["confidence"], "confidence")
    if frame < 1 or tid < 1 or w <= 0 or h <= 0 or not (0 <= conf <= 1):
        raise ValueError(f"Invalid tracker row frame={frame} id={tid}")
    left, top = max(0.0, x), max(0.0, y)
    right, bottom = min(float(width), x+w), min(float(height), y+h)
    if right <= left or bottom <= top:
        raise ValueError(f"Tracker bbox fully outside video: frame={frame}, id={tid}")
    return (f"{frame},{tid},{left+1:.6f},{top+1:.6f},"
            f"{right-left:.6f},{bottom-top:.6f},{conf:.6f},1,-1,-1")


def filter_csv(input_csv: Path, output_csv: Path, selected: set[str]) -> int:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with Path(input_csv).open(newline="", encoding="utf-8") as src, output_csv.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        if not reader.fieldnames or "video_stem" not in reader.fieldnames:
            raise ValueError(f"Missing video_stem in {input_csv}")
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row["video_stem"] in selected:
                writer.writerow(row)
                total += 1
    return total


def make_mot_workspace(*, directory: Path, gt_csv: Path, sequence_csv: Path,
                       split: str, benchmark: str, tracker: str,
                       selected: dict, predictions: dict):
    # Dependency imported here so geometry is exactly the canonical MOT materializer.
    from .mot_format import materialize_mot_ground_truth
    if not tracker or any(c in tracker for c in "/\\") or tracker in {".", ".."}:
        raise ValueError(f"Unsafe tracker name: {tracker!r}")
    selected_stems = set(selected)
    filtered_gt = directory / "selected_gt.csv"
    filtered_seq = directory / "selected_sequences.csv"
    filter_csv(gt_csv, filtered_gt, selected_stems)
    filter_csv(sequence_csv, filtered_seq, selected_stems)
    gt_root = directory / "gt"
    materialize_mot_ground_truth(gt_csv=filtered_gt, sequences_csv=filtered_seq,
                                 out_root=gt_root, benchmark=benchmark, split=split)
    tracker_root = directory / "trackers"
    tracker_data = tracker_root / f"{benchmark}-{split}" / tracker / "data"
    tracker_data.mkdir(parents=True)
    for stem, sequence in selected.items():
        w, h = int(sequence["width"]), int(sequence["height"])
        rows = [format_tracker_mot_row(row, width=w, height=h) for row in predictions.get(stem, [])]
        (tracker_data / f"{stem}.txt").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return gt_root, tracker_root


def trackeval_metrics(*, gt_root: Path, tracker_root: Path, output_root: Path,
                      benchmark: str, split: str, tracker: str, selected: dict,
                      trackeval_module: Any = None) -> tuple[list[dict], dict]:
    if trackeval_module is None:
        # Several TrackEval releases still use deprecated NumPy aliases.
        # Keep compatibility local to the evaluation process, not a vendor patch.
        import numpy as np
        for alias, built_in in (("float", float), ("int", int), ("bool", bool)):
            if alias not in np.__dict__:
                setattr(np, alias, built_in)
        try:
            import trackeval as trackeval_module
        except ImportError as exc:
            raise RuntimeError("TrackEval is required: uv add 'trackeval @ git+https://github.com/JonathonLuiten/TrackEval.git'") from exc

    dataset_cfg = {
        "GT_FOLDER": str(gt_root), "TRACKERS_FOLDER": str(tracker_root),
        "OUTPUT_FOLDER": str(output_root), "TRACKERS_TO_EVAL": [tracker],
        "BENCHMARK": benchmark, "SPLIT_TO_EVAL": split,
        "CLASSES_TO_EVAL": ["pedestrian"], "DO_PREPROC": False,
        "PRINT_CONFIG": False,
        "SEQMAP_FILE": str(gt_root / "seqmaps" / f"{benchmark}-{split}.txt"),
    }
    evaluator_cfg = {
        "USE_PARALLEL": False, "PRINT_RESULTS": False, "PRINT_CONFIG": False,
        "TIME_PROGRESS": False, "PLOT_CURVES": False,
        "OUTPUT_SUMMARY": False, "OUTPUT_DETAILED": False,
        "BREAK_ON_ERROR": True, "LOG_ON_ERROR": None,
    }
    dataset = trackeval_module.datasets.MotChallenge2DBox(dataset_cfg)
    evaluator = trackeval_module.Evaluator(evaluator_cfg)
    results, messages = evaluator.evaluate([dataset], [
        trackeval_module.metrics.HOTA(), trackeval_module.metrics.CLEAR(),
        trackeval_module.metrics.Identity(),
    ])
    dataset_name = dataset.get_name()
    if messages[dataset_name][tracker] != "Success":
        raise RuntimeError(f"TrackEval failed: {messages[dataset_name][tracker]}")
    scores = results[dataset_name][tracker]
    def flat_metric(items: dict) -> dict:
        h = items["HOTA"]
        c = items["CLEAR"]
        i = items["Identity"]
        import numpy as np
        # HOTA is mean over alpha thresholds, not HOTA(0).
        return {
            "HOTA": float(np.mean(h["HOTA"])),
            "DetA": float(np.mean(h["DetA"])),
            "AssA": float(np.mean(h["AssA"])),
            "MOTA": float(c["MOTA"]), "MOTP": float(c["MOTP"]),
            "FP": int(c["CLR_FP"]), "FN": int(c["CLR_FN"]),
            "TP": int(c["CLR_TP"]), "IDSW": int(c["IDSW"]),
            "IDF1": float(i["IDF1"]), "IDP": float(i["IDP"]), "IDR": float(i["IDR"]),
        }
    combined = flat_metric(scores["COMBINED_SEQ"]["pedestrian"])
    per_sequence = []
    for stem, info in sorted(selected.items()):
        if stem not in scores:
            raise ValueError(f"TrackEval result missing sequence {stem}")
        per_sequence.append({"split": split, "site": info.get("site", ""),
                             "video_stem": stem, **flat_metric(scores[stem]["pedestrian"])})
    return per_sequence, combined


def evaluate_tracking(*, gt_csv: Path, sequence_csv: Path, inference_status_csv: Path,
                      predictions_parquet: Path, split: str, benchmark: str, tracker: str,
                      workdir_root: Path, summary_json: Path, per_sequence_csv: Path,
                      coverage_csv_out: Path, scope: str = "observed",
                      coverage_csv: Path | None = None, backend: Any = None) -> dict:
    selected, ledger = select_sequences(sequence_csv=sequence_csv,
                                         inference_status_csv=inference_status_csv,
                                         split=split, scope=scope, coverage_csv=coverage_csv)
    if not selected:
        raise ValueError(f"No eligible sequences for TrackEval {split}; see input metadata and annotation scope")
    predictions = predictions_by_video(predictions_parquet, split=split, selected=selected,
                                       inference_status_csv=inference_status_csv)
    workdir_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"trackeval-{split}-", dir=workdir_root) as temp:
        temp_path = Path(temp)
        gt_root, tracker_root = make_mot_workspace(
            directory=temp_path, gt_csv=gt_csv, sequence_csv=sequence_csv,
            split=split, benchmark=benchmark, tracker=tracker,
            selected=selected, predictions=predictions,
        )
        per_seq, combined = trackeval_metrics(
            gt_root=gt_root, tracker_root=tracker_root, output_root=temp_path / "scores",
            benchmark=benchmark, split=split, tracker=tracker, selected=selected,
            trackeval_module=backend,
        )
    write_csv(per_sequence_csv, per_seq, ["split", "site", "video_stem", "HOTA", "DetA", "AssA", "MOTA", "MOTP", "FP", "FN", "TP", "IDSW", "IDF1", "IDP", "IDR"])
    write_csv(coverage_csv_out, ledger, ["split", "video_stem", "site", "n_gt_rows", "status", "reason", "annotation_verified"])
    from collections import Counter
    summary = {
        "split": split, "benchmark": benchmark, "tracker": tracker,
        "annotation_scope": scope,
        "annotation_coverage_verified": scope == "verified",
        "interpretation": ("reviewed fully annotated sequences" if scope == "verified" else
                           "PROVISIONAL: source Label Studio annotations may be incomplete; empty-GT videos excluded"),
        "sequences_selected": len(ledger), "sequences_evaluated": len(selected),
        "exclusions": dict(Counter(x["reason"] for x in ledger if x["reason"])),
        "metrics": combined,
    }
    write_json(summary_json, summary)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description="MOTChallenge TrackEval metrics from canonical Parquet")
    p.add_argument("--gt-csv", type=Path, required=True)
    p.add_argument("--sequences-csv", type=Path, required=True)
    p.add_argument("--inference-status-csv", type=Path, required=True)
    p.add_argument("--predictions-parquet", type=Path, required=True)
    p.add_argument("--split", choices=["val", "test"], required=True)
    p.add_argument("--benchmark", required=True)
    p.add_argument("--tracker", required=True)
    p.add_argument("--workdir-root", type=Path, required=True)
    p.add_argument("--summary-json", type=Path, required=True)
    p.add_argument("--per-sequence-csv", type=Path, required=True)
    p.add_argument("--coverage-output-csv", type=Path, required=True)
    p.add_argument("--annotation-scope", choices=["observed", "verified"], default="observed")
    p.add_argument("--coverage-csv", type=Path)
    args = p.parse_args(argv)
    result = evaluate_tracking(gt_csv=args.gt_csv, sequence_csv=args.sequences_csv,
        inference_status_csv=args.inference_status_csv, predictions_parquet=args.predictions_parquet,
        split=args.split, benchmark=args.benchmark, tracker=args.tracker,
        workdir_root=args.workdir_root, summary_json=args.summary_json,
        per_sequence_csv=args.per_sequence_csv, coverage_csv_out=args.coverage_output_csv,
        scope=args.annotation_scope, coverage_csv=args.coverage_csv)
    print(f"TrackEval {args.split}: {result}")


if __name__ == "__main__":
    main()
