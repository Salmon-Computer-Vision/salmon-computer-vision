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
    p.add_argument("--device", default="0")
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
    p.add_argument("--use-ray", action="store_true")
    p.add_argument("--ray-tmp-dir", default=None)
    p.add_argument("--close-mosaic", type=int, default=10)
    p.add_argument("--dropout", type=float, default=0.0)
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

    if args.use_ray:
        import json
        import ray

        ray_tmp_dir = Path(args.ray_tmp_dir).resolve() if args.ray_tmp_dir else None
        if ray_tmp_dir is not None:
            ray_tmp_dir.mkdir(parents=True, exist_ok=True)
            spill_dir = ray_tmp_dir / "spill"
            spill_dir.mkdir(parents=True, exist_ok=True)

            ray.init(
                _temp_dir=str(ray_tmp_dir),
                _system_config={
                    "object_spilling_config": json.dumps({
                        "type": "filesystem",
                        "params": {"directory_path": str(spill_dir)}
                    }),
                },
                ignore_reinit_error=True,
            )

    if args.stage1_iterations is not None:
        run_two_stage_tune(
            model_path=model_path,
            data_yaml=data_yaml,
            output_dir=out_dir,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            stage1_iterations=args.stage1_iterations,
            stage2_iterations=args.stage2_iterations,
            workers=args.workers,
            patience=args.patience,
            optimizer=args.optimizer,
            use_ray=args.use_ray,
            best_hyp_json=Path(args.best_hyp_json) if args.best_hyp_json else None,
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
            device=args.device,
            iterations=iterations,
            workers=args.workers,
            patience=args.patience,
            optimizer=args.optimizer,
            use_ray=args.use_ray,
            train_args=train_args,
        )
