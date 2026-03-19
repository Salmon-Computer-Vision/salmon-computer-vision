from pathlib import Path
from typing import Dict, Optional, Tuple, Any
import yaml

def coord_mode(x: float, y: float, w: float, h: float) -> str:
    """
    Infer coordinate mode for Label Studio:
    - 'percent'   : typical LS UI export (0..100)
    - 'normalized': already 0..1
    - 'pixel'     : values > 100 (needs video width/height)
    """
    mx = max(x, y, w, h)
    if mx <= 1.0000001:       # already normalized
        return "normalized"
    if mx <= 100.0000001:     # percent
        return "percent"
    return "pixel"


def to_yolo(
    x: float,
    y: float,
    w: float,
    h: float,
    vid_w: int,
    vid_h: int,
    forced_mode: Optional[str] = None,
) -> Tuple[float, float, float, float]:
    """
    Convert LS-style box to YOLO (xc, yc, w, h) in [0,1].

    :param forced_mode: One of {"percent", "normalized", "pixel", None/"auto"}.
                        If None or "auto", infer from values.
    """
    mode = forced_mode or "auto"
    if mode == "auto":
        mode = coord_mode(x, y, w, h)

    if mode == "normalized":
        xc = x + w / 2.0
        yc = y + h / 2.0
        wn = w
        hn = h
    elif mode == "percent":
        xc = (x + w / 2.0) / 100.0
        yc = (y + h / 2.0) / 100.0
        wn = w / 100.0
        hn = h / 100.0
    elif mode == "pixel":
        xc = (x + w / 2.0) / float(vid_w) if vid_w else 0.0
        yc = (y + h / 2.0) / float(vid_h) if vid_h else 0.0
        wn = w / float(vid_w) if vid_w else 0.0
        hn = h / float(vid_h) if vid_h else 0.0
    else:
        raise ValueError(f"Unknown coord_mode: {forced_mode!r}")

    # clamp to [0,1]
    xc = min(max(xc, 0.0), 1.0)
    yc = min(max(yc, 0.0), 1.0)
    wn = min(max(wn, 0.0), 1.0)
    hn = min(max(hn, 0.0), 1.0)
    return xc, yc, wn, hn

def load_class_map_from_yolo_yaml(yaml_path: Path) -> Dict[str, int]:
    """
    Load a YOLO-style data.yaml and return a mapping: class_name -> class_id

    Expects something like:

      names:
        0: Coho
        1: Bull
        2: Rainbow
        ...

    or:

      names: [Coho, Bull, Rainbow, ...]
    """
    data: Any = yaml.safe_load(Path(yaml_path).read_text())
    names = data.get("names")
    if names is None:
        raise ValueError(f"'names' not found in {yaml_path}")

    class_map: Dict[str, int] = {}

    if isinstance(names, dict):
        # {0: 'Coho', 1: 'Bull', ...} (keys can be int or str)
        for k, v in names.items():
            try:
                idx = int(k)
            except Exception:
                raise ValueError(f"Invalid class index {k!r} in names of {yaml_path}")
            label = str(v)
            class_map[label] = idx
    elif isinstance(names, (list, tuple)):
        # ['Coho', 'Bull', 'Rainbow', ...]
        for idx, label in enumerate(names):
            class_map[str(label)] = idx
    else:
        raise ValueError(f"Unsupported 'names' structure in {yaml_path}: {type(names)}")

    return class_map

