from __future__ import annotations

import argparse
import json
from pathlib import Path

from object_detection.training.train_best import train_best_yolo


def main() -> None:
    p = argparse.ArgumentParser(description="Train YOLO on full dataset using best tuned args.yaml")
    p.add_argument("--data-yaml", required=True, help="Full dataset data.yaml")
    p.add_argument("--model", required=True, help="Base model checkpoint, e.g. yolov8n.pt")
    p.add_argument("--args-yaml", required=True, help="args.yaml from best tuning trial")
    p.add_argument("--out-dir", required=True, help="Training output project directory")
    p.add_argument("--run-name", default="train_full_best")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--device", default="0")
    p.add_argument("--batch", type=int, default=None)
    p.add_argument("--imgsz", type=int, default=None)
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--summary-json", default=None)
    args = p.parse_args()

    summary = train_best_yolo(
        model_path=args.model,
        data_yaml=args.data_yaml,
        args_yaml=Path(args.args_yaml),
        out_dir=Path(args.out_dir),
        run_name=args.run_name,
        epochs=args.epochs,
        device=args.device,
        batch=args.batch,
        imgsz=args.imgsz,
        workers=args.workers,
    )

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"Done. project={summary['project']} "
        f"name={summary['name']} "
        f"data={summary['data']}"
    )
