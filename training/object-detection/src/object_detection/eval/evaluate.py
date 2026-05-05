from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from ultralytics import YOLO


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _to_builtin(x: Any) -> Any:
    if hasattr(x, "item"):
        try:
            return x.item()
        except Exception:
            pass
    return x


def _load_class_names(data_yaml: Path) -> Dict[int, str]:
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    names = data.get("names", {})

    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    if isinstance(names, list):
        return {i: str(v) for i, v in enumerate(names)}
    return {}


def _build_per_class_records(
    *,
    class_names: Dict[int, str],
    class_ids: List[int],
    ap: Optional[List[float]],
    ap50: Optional[List[float]],
    precision: Optional[List[float]],
    recall: Optional[List[float]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for i, class_id in enumerate(class_ids):
        rec: Dict[str, Any] = {
            "class_id": int(class_id),
            "class_name": class_names.get(int(class_id), str(class_id)),
        }
        if ap is not None and i < len(ap):
            rec["ap"] = float(_to_builtin(ap[i]))
        if ap50 is not None and i < len(ap50):
            rec["ap50"] = float(_to_builtin(ap50[i]))
        if precision is not None and i < len(precision):
            rec["precision"] = float(_to_builtin(precision[i]))
        if recall is not None and i < len(recall):
            rec["recall"] = float(_to_builtin(recall[i]))
        records.append(rec)

    return records


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
    save_json_plot: Path | None = None,
) -> Dict[str, Any]:

    model = YOLO(model_path)
    data_yaml_path = Path(data_yaml).resolve()

    kwargs: Dict[str, Any] = {
        "data": str(data_yaml_path),
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

    class_names = _load_class_names(data_yaml_path)

    ap = None
    ap50 = None
    precision = None
    recall = None
    per_class_records: List[Dict[str, Any]] = []

    try:
        class_ids = [int(_to_builtin(x)) for x in results.box.ap_class_index]
        ap_vals = [float(_to_builtin(x)) for x in results.box.ap]
        ap50_vals = [float(_to_builtin(x)) for x in results.box.ap50]
        precision_vals = [float(_to_builtin(x)) for x in results.box.p]
        recall_vals = [float(_to_builtin(x)) for x in results.box.r]

        ap = {cid: val for cid, val in zip(class_ids, ap_vals)}
        ap50 = {cid: val for cid, val in zip(class_ids, ap50_vals)}
        precision = {cid: val for cid, val in zip(class_ids, precision_vals)}
        recall = {cid: val for cid, val in zip(class_ids, recall_vals)}

        per_class_records = _build_per_class_records(
            class_names=class_names,
            class_ids=class_ids,
            ap=ap_vals,
            ap50=ap50_vals,
            precision=precision_vals,
            recall=recall_vals,
        )
    except Exception:
        pass

    summary = {
        "model_path": str(Path(model_path).resolve()),
        "data_yaml": str(data_yaml_path),
        "split": split,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "workers": workers,
        "map50": float(_to_builtin(getattr(results.box, "map50", None))) if hasattr(results, "box") and getattr(results.box, "map50", None) is not None else None,
        "map50_95": float(_to_builtin(getattr(results.box, "map", None))) if hasattr(results, "box") and getattr(results.box, "map", None) is not None else None,
        "mp": float(_to_builtin(getattr(results.box, "mp", None))) if hasattr(results, "box") and getattr(results.box, "mp", None) is not None else None,
        "mr": float(_to_builtin(getattr(results.box, "mr", None))) if hasattr(results, "box") and getattr(results.box, "mr", None) is not None else None,
        "ap": ap,
        "ap50": ap50,
        "p": precision,
        "r": recall,
        "per_class_metrics": per_class_records,
        "fitness": float(_to_builtin(getattr(results, "fitness", None))) if getattr(results, "fitness", None) is not None else None,
    }

    if save_json_metrics is not None:
        save_json(save_json_metrics, summary)

    if save_json_plot is not None:
        plot_rows = [
            {
                "class_id": rec["class_id"],
                "class_name": rec["class_name"],
                "ap": rec.get("ap"),
                "ap50": rec.get("ap50"),
                "precision": rec.get("precision"),
                "recall": rec.get("recall"),
            }
            for rec in per_class_records
        ]
        save_json(save_json_plot, plot_rows)

    return summary
