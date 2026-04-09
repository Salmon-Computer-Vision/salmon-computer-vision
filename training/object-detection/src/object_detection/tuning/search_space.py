from __future__ import annotations

from typing import Dict, Any


def default_tune_space() -> Dict[str, Any]:
    """
    Conservative YOLOv8 detect search space for a baseline tuning run.

    These keys are chosen to be practical for object detection and to avoid
    blowing up training time too much.
    """
    return {
        # Optimizer / schedule
        "lr0": (1e-4, 5e-2),           # initial learning rate
        "lrf": (0.01, 0.5),            # final lr fraction
        "momentum": (0.80, 0.98),
        "weight_decay": (0.0, 1e-3),
        "warmup_epochs": (0.0, 5.0),
        "warmup_momentum": (0.0, 0.95),

        # Loss balance
        "box": (5.0, 12.0),
        "cls": (0.2, 4.0),
        "dfl": (0.5, 2.5),

        # Color aug
        "hsv_h": (0.0, 0.05),
        "hsv_s": (0.0, 0.9),
        "hsv_v": (0.0, 0.9),

        # Geometric aug
        "degrees": (0.0, 10.0),
        "translate": (0.0, 0.2),
        "scale": (0.0, 0.7),
        "shear": (0.0, 5.0),
        "perspective": (0.0, 0.001),
        "flipud": (0.0, 0.5),
        "fliplr": (0.0, 0.5),

        # Mix aug
        "mosaic": (0.0, 1.0),
        "mixup": (0.0, 0.3),
        "copy_paste": (0.0, 0.3),
    }


def narrowed_tune_space(best: Dict[str, float], frac: float = 0.35) -> Dict[str, Any]:
    """
    Build a narrower box around a previous best run.
    """
    out: Dict[str, Any] = {}
    for k, v in best.items():
        if not isinstance(v, (int, float)):
            continue
        lo = v * (1.0 - frac)
        hi = v * (1.0 + frac)

        # Keep known nonnegative params sane
        if k in {
            "lr0", "lrf", "weight_decay", "warmup_epochs",
            "box", "cls", "dfl",
            "hsv_h", "hsv_s", "hsv_v",
            "degrees", "translate", "scale", "shear",
            "perspective", "flipud", "fliplr",
            "mosaic", "mixup", "copy_paste",
        }:
            lo = max(0.0, lo)

        # Cap probability-like params
        if k in {
            "lrf", "warmup_momentum", "hsv_h", "hsv_s", "hsv_v",
            "translate", "scale", "perspective", "flipud", "fliplr",
            "mosaic", "mixup", "copy_paste", "momentum",
        }:
            hi = min(1.0 if k != "momentum" else 0.999, hi)

        out[k] = (lo, hi)
    return out
