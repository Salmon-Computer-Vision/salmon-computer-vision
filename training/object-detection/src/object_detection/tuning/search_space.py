from __future__ import annotations

from typing import Dict, Any
from ray import tune


def default_tune_space() -> Dict[str, Any]:
    return {
        "lr0": tune.loguniform(1e-4, 5e-2),
        "lrf": tune.uniform(0.01, 0.5),
        "momentum": tune.uniform(0.80, 0.98),
        "weight_decay": tune.loguniform(1e-6, 1e-3),
        "warmup_epochs": tune.uniform(0.0, 5.0),
        "warmup_momentum": tune.uniform(0.0, 0.95),

        # Loss balance
        "box": tune.uniform(5.0, 12.0),
        "cls": tune.uniform(0.2, 4.0),
        "dfl": tune.uniform(0.5, 2.5),

        # Colour aug
        "hsv_h": tune.uniform(0.0, 0.05),
        "hsv_s": tune.uniform(0.0, 0.9),
        "hsv_v": tune.uniform(0.0, 0.9),

        # Geometric aug
        "degrees": tune.uniform(0.0, 10.0),
        "translate": tune.uniform(0.0, 0.2),
        "scale": tune.uniform(0.0, 0.7),
        "shear": tune.uniform(0.0, 5.0),
        "perspective": tune.uniform(0.0, 0.001),
        "flipud": tune.uniform(0.0, 0.0), # Disable flip up and down augmentation
        "fliplr": tune.uniform(0.0, 0.5),

        # Mix aug
        "mosaic": tune.uniform(0.0, 1.0),
        "mixup": tune.uniform(0.0, 0.3),
        "copy_paste": tune.uniform(0.0, 0.3),
    }


def narrowed_tune_space(best: Dict[str, float], frac: float = 0.35) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in best.items():
        if not isinstance(v, (int, float)):
            continue

        lo = v * (1.0 - frac)
        hi = v * (1.0 + frac)

        if k in {
            "lr0", "lrf", "weight_decay", "warmup_epochs",
            "box", "cls", "dfl",
            "hsv_h", "hsv_s", "hsv_v",
            "degrees", "translate", "scale", "shear",
            "perspective", "flipud", "fliplr",
            "mosaic", "mixup", "copy_paste",
        }:
            lo = max(0.0, lo)

        if k in {"lr0", "weight_decay"}:
            lo = max(lo, 1e-9)
            hi = max(hi, lo * 1.0001)
            out[k] = tune.loguniform(lo, hi)
        else:
            if k in {
                "lrf", "warmup_momentum", "hsv_h", "hsv_s", "hsv_v",
                "translate", "scale", "perspective", "flipud", "fliplr",
                "mosaic", "mixup", "copy_paste",
            }:
                hi = min(1.0, hi)
            if k == "momentum":
                hi = min(0.999, hi)
            out[k] = tune.uniform(lo, hi)

    return out
