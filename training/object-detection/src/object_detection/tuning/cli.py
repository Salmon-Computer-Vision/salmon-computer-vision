from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.tuning.tune import run_two_stage_tune, run_ultralytics_tune


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Tune YOLO hyperparameters on a small dataset manifest.")
    p.add_argument("--data-yaml", required=True, help="Usually data_small.yaml")
    p.add_argument("--model", default="yolov8n.pt", help="Base checkpoint, e.g. yolov8n.pt")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=960)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--optimizer", default="auto")

    p.add_argument("--iterations", type=int, default=None,
                   help="Single-stage tuning iterations")
    p.add_argument("--stage1-iterations", type=int, default=None,
                   help="Two-stage tuning: broad search iterations")
    p.add_argument("--stage2-iterations", type=int, default=0,
                   help="Two-stage tuning: narrow search iterations")
    p.add_argument("--best-hyp-json", default=None,
                   help="Optional JSON of best hyperparameters for stage 2")
    p.add_argument("--device", default=None)
    p.add_argument("--use-ray", action="store_true")
    p.add_argument("--gpu-per-trial", default=None)
    p.add_argument("--close-mosaic", type=int, default=10)
    p.add_argument("--dropout", type=float, default=0.0)
    p.add_argument("--resume", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    out_dir = Path(args.out_dir).resolve()
    data_yaml = str(Path(args.data_yaml).resolve())
    model_path = str(Path(args.model).resolve()) if Path(args.model).exists() else args.model

    train_args = {
        "close_mosaic": args.close_mosaic,
        "dropout": args.dropout,
    }

    if args.stage1_iterations is not None:
        run_two_stage_tune(
            model_path=model_path,
            data_yaml=data_yaml,
            output_dir=out_dir,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            stage1_iterations=args.stage1_iterations,
            stage2_iterations=args.stage2_iterations,
            workers=args.workers,
            patience=args.patience,
            optimizer=args.optimizer,
            device=args.device,
            use_ray=args.use_ray,
            best_hyp_json=Path(args.best_hyp_json) if args.best_hyp_json else None,
            gpu_per_trial=args.gpu_per_trial,
            resume=args.resume,
            train_args=train_args,
        )
    else:
        iterations = args.iterations if args.iterations is not None else 25
        run_ultralytics_tune(
            model_path=model_path,
            data_yaml=data_yaml,
            output_dir=out_dir,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            iterations=iterations,
            workers=args.workers,
            patience=args.patience,
            optimizer=args.optimizer,
            device=args.device,
            use_ray=args.use_ray,
            gpu_per_trial=args.gpu_per_trial,
            resume=args.resume,
            train_args=train_args,
        )
