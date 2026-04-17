from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
import numpy as np

from ultralytics import YOLO


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_yolo(
    *,
    model_path: str,
    data_yaml: str,
    out_dir: Path,
    run_name: str,
    split: str = "test",
    imgsz: int = 640,
    batch: int = 32,
    device: str = "0",
    workers: int = 8,
    conf: float | None = None,
    iou: float | None = None,
    save_json_metrics: Path | None = None,
) -> Dict[str, Any]:
    model = YOLO(model_path)

    kwargs: Dict[str, Any] = {
        "data": str(Path(data_yaml).resolve()),
        "split": split,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "workers": workers,
        "project": str(out_dir.resolve()),
        "name": run_name,
        "plots": True,
        "save_json": True,
    }

    if conf is not None:
        kwargs["conf"] = conf
    if iou is not None:
        kwargs["iou"] = iou

    results = model.val(**kwargs)

    ap = None
    ap50 = None
    try:
        print(results.box.ap_class_index)
        print(results.box.ap50)
        ap = dict(zip(np.array(results.box.ap_class_index).astype(int), results.box.ap))
        ap50 = dict(zip(np.array(results.box.ap_class_index).astype(int), results.box.ap50))
    except:
        pass

    summary = {
        "model_path": str(Path(model_path).resolve()),
        "data_yaml": str(Path(data_yaml).resolve()),
        "split": split,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "workers": workers,
        "map50": getattr(results.box, "map50", None) if hasattr(results, "box") else None,
        "map50_95": getattr(results.box, "map", None) if hasattr(results, "box") else None,
        "mp": getattr(results.box, "mp", None) if hasattr(results, "box") else None,
        "mr": getattr(results.box, "mr", None) if hasattr(results, "box") else None,
        "ap": ap,
        "ap50": ap50,
        "fitness": getattr(results, "fitness", None),
    }

    if save_json_metrics is not None:
        save_json(save_json_metrics, summary)

    return summary
