from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.eval.evaluate import evaluate_yolo


def main() -> None:
    p = argparse.ArgumentParser(description="Evaluate a trained YOLO model on a dataset split")
    p.add_argument("--model", required=True, help="Path to trained weights, usually best.pt")
    p.add_argument("--data-yaml", required=True, help="Dataset YAML, usually yolo_workdir/data.yaml")
    p.add_argument("--out-dir", required=True, help="Evaluation project directory")
    p.add_argument("--run-name", default="eval_test")
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--device", default="0")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--conf", type=float, default=None)
    p.add_argument("--iou", type=float, default=None)
    p.add_argument("--summary-json", default=None)
    p.add_argument("--plot-json", default=None)
    args = p.parse_args()

    summary = evaluate_yolo(
        model_path=args.model,
        data_yaml=args.data_yaml,
        out_dir=Path(args.out_dir),
        run_name=args.run_name,
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        conf=args.conf,
        iou=args.iou,
        save_json_metrics=Path(args.summary_json) if args.summary_json else None,
        save_json_plot=Path(args.plot_json) if args.plot_json else None,
    )

    print(
        f"Done. split={summary['split']} "
        f"mAP50={summary['map50']} "
        f"mAP50-95={summary['map50_95']}"
    )
