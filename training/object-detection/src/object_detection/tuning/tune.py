from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ultralytics import YOLO

from object_detection.tuning.search_space import default_tune_space, narrowed_tune_space


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_best_hyp_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_ultralytics_tune(
    *,
    model_path: str,
    data_yaml: str,
    output_dir: Path,
    epochs: int,
    imgsz: int,
    batch: int,
    device: str,
    iterations: int,
    workers: int = 8,
    patience: int = 20,
    optimizer: str = "auto",
    use_ray: bool = False,
    space: Optional[Dict[str, Any]] = None,
    train_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run Ultralytics tuning and save a compact config snapshot.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(model_path)

    tune_space = space or default_tune_space()
    extra_args = train_args or {}

    result = model.tune(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        iterations=iterations,
        workers=workers,
        patience=patience,
        optimizer=optimizer,
        project=str(output_dir),
        name="tune",
        use_ray=use_ray,
        space=tune_space,
        **extra_args,
    )

    summary = {
        "model_path": model_path,
        "data_yaml": data_yaml,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "iterations": iterations,
        "workers": workers,
        "patience": patience,
        "optimizer": optimizer,
        "use_ray": use_ray,
        "space_keys": sorted(tune_space.keys()),
        "result_repr": str(result),
    }
    write_json(output_dir / "tune_run_config.json", summary)
    return summary


def run_two_stage_tune(
    *,
    model_path: str,
    data_yaml: str,
    output_dir: Path,
    epochs: int,
    imgsz: int,
    batch: int,
    device: str,
    stage1_iterations: int,
    stage2_iterations: int,
    workers: int = 8,
    patience: int = 20,
    optimizer: str = "auto",
    use_ray: bool = False,
    best_hyp_json: Optional[Path] = None,
    train_args: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Stage 1: broad search
    Stage 2: narrower search around a previous best if provided
    """
    stage1_dir = output_dir / "stage1"
    run_ultralytics_tune(
        model_path=model_path,
        data_yaml=data_yaml,
        output_dir=stage1_dir,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        iterations=stage1_iterations,
        workers=workers,
        patience=patience,
        optimizer=optimizer,
        use_ray=use_ray,
        space=default_tune_space(),
        train_args=train_args,
    )

    if best_hyp_json is not None and best_hyp_json.exists() and stage2_iterations > 0:
        best = load_best_hyp_json(best_hyp_json)
        stage2_dir = output_dir / "stage2"
        run_ultralytics_tune(
            model_path=model_path,
            data_yaml=data_yaml,
            output_dir=stage2_dir,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            iterations=stage2_iterations,
            workers=workers,
            patience=patience,
            optimizer=optimizer,
            use_ray=use_ray,
            space=narrowed_tune_space(best),
            train_args=train_args,
        )
