#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CANDIDATE_METRIC_COLUMNS = [
    "metrics/mAP50-95(B)",
    "metrics/mAP50(B)",
    "fitness",
    "metrics/precision(B)",
    "metrics/recall(B)",
]


def read_last_csv_row(path: Path) -> Optional[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1]


def pick_metric_column(row: Dict[str, str]) -> Optional[str]:
    for col in CANDIDATE_METRIC_COLUMNS:
        if col in row and row[col] not in ("", None):
            return col
    return None


def safe_float(x: object) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def find_best_weights(trial_dir: Path) -> Optional[Path]:
    candidates = [
        trial_dir / "weights" / "best.pt",
        trial_dir / "weights" / "last.pt",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def summarize_trials(tune_root: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for trial_dir in sorted(p for p in tune_root.iterdir() if p.is_dir()):
        results_csv = trial_dir / "results.csv"
        if not results_csv.exists():
            continue

        last = read_last_csv_row(results_csv)
        if last is None:
            continue

        metric_col = pick_metric_column(last)
        metric_val = safe_float(last.get(metric_col)) if metric_col else None
        epoch_val = safe_float(last.get("epoch"))

        row: Dict[str, object] = {
            "trial": trial_dir.name,
            "results_csv": str(results_csv),
            "metric_name": metric_col or "",
            "metric_value": metric_val,
            "epoch": int(epoch_val) if epoch_val is not None else None,
            "best_weights": str(find_best_weights(trial_dir)) if find_best_weights(trial_dir) else "",
        }

        # keep a few common columns if present
        for key in [
            "train/box_loss",
            "train/cls_loss",
            "train/dfl_loss",
            "val/box_loss",
            "val/cls_loss",
            "val/dfl_loss",
            "metrics/precision(B)",
            "metrics/recall(B)",
            "metrics/mAP50(B)",
            "metrics/mAP50-95(B)",
            "lr/pg0",
            "lr/pg1",
            "lr/pg2",
        ]:
            if key in last:
                row[key] = last[key]

        rows.append(row)

    return rows


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = sorted({k for row in rows for k in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize Ultralytics Ray Tune trial folders.")
    ap.add_argument("--tune-root", required=True, help="Path containing tune, tune1, tune2, ... trial dirs")
    ap.add_argument("--out-csv", required=True, help="Summary CSV")
    ap.add_argument("--out-json", required=True, help="Best-trial JSON")
    args = ap.parse_args()

    tune_root = Path(args.tune_root)
    rows = summarize_trials(tune_root)

    # sort best-first by metric_value if available
    rows.sort(
        key=lambda r: (-1e18 if r["metric_value"] is None else -float(r["metric_value"]), str(r["trial"]))
    )

    write_csv(Path(args.out_csv), rows)

    best = rows[0] if rows else {}
    write_json(Path(args.out_json), best)

    if best:
        print(
            f"Best trial: {best['trial']} | "
            f"{best['metric_name']}={best['metric_value']} | "
            f"weights={best['best_weights']}"
        )
    else:
        print("No valid trial results found.")


if __name__ == "__main__":
    main()
