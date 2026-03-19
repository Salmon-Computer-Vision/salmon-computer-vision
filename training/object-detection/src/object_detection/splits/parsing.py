import re
from pathlib import Path
from typing import Dict, Tuple, Optional
from collections import Counter


_STEM_RE = re.compile(
    r"""
    ^
    (?P<prefix>.+?)                 # ORG-site-device-id (up to first underscore)
    _
    (?P<date>\d{8})                 # YYYYMMDD
    _
    (?P<time>\d{6})                 # HHMMSS
    _
    (?P<suffix>.+)                  # M / etc
    $
    """,
    re.VERBOSE,
)

def parse_video_stem(video_stem: str) -> Optional[Dict[str, str]]:
    """
    Parse:
      HIRMD-tankeeah-jetson-0_20250714_012827_M
    into:
      org="HIRMD", site="tankeeah", device="jetson-0", date="20250714", time="012827"
    """
    m = _STEM_RE.match(video_stem)
    if not m:
        return None

    prefix = m.group("prefix")
    date = m.group("date")
    time = m.group("time")

    parts = prefix.split("-")
    if len(parts) < 3:
        return None

    org = parts[0]
    site = parts[1]
    device = "-".join(parts[2:])  # includes jetson-0, jetsonorin-1, etc.

    return {"org": org, "site": site, "device": device, "date": date, "time": time}


def time_bucket(hhmmss: str) -> str:
    """Coarse time-of-day buckets based on HH."""
    try:
        hh = int(hhmmss[0:2])
    except Exception:
        return "unknown"
    if 0 <= hh <= 5:
        return "night"
    if 6 <= hh <= 11:
        return "morning"
    if 12 <= hh <= 17:
        return "afternoon"
    if 18 <= hh <= 23:
        return "evening"
    return "unknown"


def density_bin(n_boxes: int) -> str:
    """Bins for boxes per frame."""
    if n_boxes <= 0:
        return "0"
    if n_boxes == 1:
        return "1"
    if n_boxes == 2:
        return "2"
    if 3 <= n_boxes <= 4:
        return "3-4"
    if 5 <= n_boxes <= 9:
        return "5-9"
    return "10+"

def ar_bin(w: float, h: float) -> str:
    """
    Aspect ratio bins based on w/h.
    w,h are YOLO normalized widths/heights in [0,1].
    """
    if w <= 0 or h <= 0:
        return "invalid"
    r = w / h

    # You can tune these thresholds, but this is a good start:
    if r < 0.67:
        return "tall"        # height-dominant
    if r <= 1.5:
        return "square"      # roughly square-ish
    return "wide"            # width-dominant

def area_bin(area: float) -> str:
    """
    Bin YOLO normalized bbox area (w*h) in [0,1].
    Tune thresholds if needed.
    """
    if area <= 0:
        return "0"
    if area < 0.0025:
        return "<0.0025"
    if area < 0.01:
        return "0.0025-0.01"
    if area < 0.04:
        return "0.01-0.04"
    if area < 0.16:
        return "0.04-0.16"
    return ">=0.16"


def safe_float(x: str, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def parse_frame_idx(filename: str) -> Optional[int]:
    # frame_000123.txt
    m = re.match(r"^frame_(\d+)\.txt$", filename)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def read_yolo_label(path: Path) -> Tuple[int, Counter, Counter, Counter]:
    """
    Returns:
      n_boxes,
      class_counts (class_id -> count),
      area_bins (area_bin -> count)
    """
    n_boxes = 0
    class_counts: Counter = Counter()
    area_counts: Counter = Counter()
    ar_counts: Counter = Counter()

    try:
        txt = path.read_text().strip()
    except Exception:
        return 0, Counter(), Counter(), Counter()

    if not txt:
        return 0, Counter(), Counter(), Counter()

    for line in txt.splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls = parts[0]
        w = safe_float(parts[3], 0.0)
        h = safe_float(parts[4], 0.0)
        try:
            cls_id = int(cls)
        except Exception:
            continue
        n_boxes += 1
        class_counts[cls_id] += 1
        area_counts[area_bin(w * h)] += 1
        ar_counts[ar_bin(w, h)] += 1

    return n_boxes, class_counts, area_counts, ar_counts

