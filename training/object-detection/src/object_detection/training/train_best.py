from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from ultralytics import YOLO


ALLOWED_ARGS = {
    # optimizer / schedule
    "lr0",
    "lrf",
    "momentum",
    "weight_decay",
    "warmup_epochs",
    "warmup_momentum",
    "warmup_bias_lr",
    "optimizer",

    # loss weights
    "box",
    "cls",
    "dfl",

    # augmentation
    "hsv_h",
    "hsv_s",
    "hsv_v",
    "degrees",
    "translate",
    "scale",
    "shear",
    "perspective",
    "flipud",
    "fliplr",
    "mosaic",
    "mixup",
    "copy_paste",
    "close_mosaic",

    # training behavior
    "imgsz",
    "batch",
    "patience",
    "dropout",
    "workers",
    "multi_scale",
    "cos_lr",
    "cache",
    "rect",
    "single_cls",
    "amp",
    "freeze",
    "seed",
    "deterministic",
}


def load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML: {path}")
    return data


def extract_train_overrides(args_yaml: Path) -> Dict[str, Any]:
    raw = load_yaml(args_yaml)
    out: Dict[str, Any] = {}

    for key, value in raw.items():
        if key in ALLOWED_ARGS:
            out[key] = value

    return out


def train_best_yolo(
    *,
    model_path: str,
    data_yaml: str,
    args_yaml: Path,
    out_dir: Path,
    run_name: str,
    epochs: int,
    device: str | None,
    batch: int | None = None,
    imgsz: int | None = None,
    workers: int | None = None,
) -> Dict[str, Any]:
    overrides = extract_train_overrides(args_yaml)

    overrides["data"] = str(Path(data_yaml).resolve())
    overrides["project"] = str(out_dir.resolve())
    overrides["name"] = run_name
    overrides["epochs"] = epochs

    if device is not None and device != "":
        overrides["device"] = device
    else:
        # Let Ultralytics decide
        overrides.pop("device", None)

    if batch is not None:
        overrides["batch"] = batch
    if imgsz is not None:
        overrides["imgsz"] = imgsz
    if workers is not None:
        overrides["workers"] = workers

    model = YOLO(model_path)
    results = model.train(**overrides)

    return {
        "results_repr": str(results),
        "project": overrides["project"],
        "name": overrides["name"],
        "data": overrides["data"],
        "epochs": overrides["epochs"],
        "device": overrides.get("device", ""),
        "batch": overrides.get("batch", ""),
        "imgsz": overrides.get("imgsz", ""),
        "workers": overrides.get("workers", ""),
    }
