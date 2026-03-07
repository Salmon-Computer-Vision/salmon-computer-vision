#!/usr/bin/env python3
"""
make_splits.py

Group-wise stratified-ish split for unpacked YOLO label files.

- Input: unpacked labels directory that looks like:
    <root>/<video_stem>/frame_000123.txt

  where video_stem looks like:
    ORG-site-device-id_YYYYMMDD_HHMMSS_M

- Output:
    out_dir/train.txt
    out_dir/val.txt
    out_dir/test.txt
    out_dir/group_assignments.csv
    out_dir/split_report.json

Split unit (to prevent leakage): group_id = site + device + date(YYYYMMDD)
Balancing objectives (soft): class counts, time-of-day, density bins, box area bins.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterable, Any
from collections import defaultdict, Counter

# -----------------------------
# Parsing helpers
# -----------------------------

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


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class FrameRecord:
    rel_path: str            # relative path to label file within labels_root
    video_stem: str
    frame_idx: int
    org: str
    site: str
    device: str
    date: str                # YYYYMMDD
    tod: str                 # time-of-day bucket

    n_boxes: int
    class_counts: Counter    # class_id -> count
    density_bin: str
    area_bins: Counter       # area_bin -> count (counts per box)


@dataclass
class GroupStats:
    group_id: str
    site: str
    device: str
    date: str

    n_frames: int
    n_boxes: int

    class_counts: Counter
    tod_counts: Counter
    density_counts: Counter
    area_counts: Counter

    # list of frame rel_paths (for manifest writing)
    frame_paths: List[str]


# -----------------------------
# Scanning labels
# -----------------------------

def iter_label_files(labels_root: Path) -> Iterable[Path]:
    # Expect structure: labels_root/<video_stem>/frame_000123.txt
    for p in labels_root.rglob("frame_*.txt"):
        if p.is_file():
            yield p


def parse_frame_idx(filename: str) -> Optional[int]:
    # frame_000123.txt
    m = re.match(r"^frame_(\d+)\.txt$", filename)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def read_yolo_label(path: Path) -> Tuple[int, Counter, Counter]:
    """
    Returns:
      n_boxes,
      class_counts (class_id -> count),
      area_bins (area_bin -> count)
    """
    n_boxes = 0
    class_counts: Counter = Counter()
    area_counts: Counter = Counter()

    try:
        txt = path.read_text().strip()
    except Exception:
        return 0, Counter(), Counter()

    if not txt:
        return 0, Counter(), Counter()

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

    return n_boxes, class_counts, area_counts


def build_groups(
    labels_root: Path,
    sites_keep: set[str],
    seed: int,
    limit: Optional[int] = None,
) -> Dict[str, GroupStats]:
    """
    Build per-group aggregates. Group id = site|device|date.
    """
    rnd = random.Random(seed)

    files = list(iter_label_files(labels_root))
    files.sort()
    if limit is not None:
        rnd.shuffle(files)
        files = files[:limit]

    groups: Dict[str, GroupStats] = {}

    skipped = 0
    for f in files:
        video_stem = f.parent.name
        meta = parse_video_stem(video_stem)
        if meta is None:
            skipped += 1
            continue

        site = meta["site"]
        if sites_keep and site not in sites_keep:
            continue

        frame_idx = parse_frame_idx(f.name)
        if frame_idx is None:
            skipped += 1
            continue

        n_boxes, class_counts, area_counts = read_yolo_label(f)
        # If you ever include negatives, you may want to keep empty files too.
        # For now, assume label files exist only when boxes exist.
        dens_bin = density_bin(n_boxes)
        tod = time_bucket(meta["time"])

        rel_path = str(f.relative_to(labels_root))

        group_id = f"{site}|{meta['device']}|{meta['date']}"
        if group_id not in groups:
            groups[group_id] = GroupStats(
                group_id=group_id,
                site=site,
                device=meta["device"],
                date=meta["date"],
                n_frames=0,
                n_boxes=0,
                class_counts=Counter(),
                tod_counts=Counter(),
                density_counts=Counter(),
                area_counts=Counter(),
                frame_paths=[],
            )

        g = groups[group_id]
        g.n_frames += 1
        g.n_boxes += n_boxes
        g.class_counts.update(class_counts)
        g.tod_counts[tod] += 1
        g.density_counts[dens_bin] += 1
        g.area_counts.update(area_counts)
        g.frame_paths.append(rel_path)

    if skipped:
        print(f"[make_splits] skipped {skipped} files due to parse issues")
    print(f"[make_splits] groups={len(groups)} from label files={len(files)}")
    return groups


# -----------------------------
# Split objective
# -----------------------------

def normalize_counter(c: Counter) -> Dict[Any, float]:
    s = float(sum(c.values()))
    if s <= 0:
        return {}
    return {k: v / s for k, v in c.items()}


def l1_dist(p: Dict[Any, float], q: Dict[Any, float], keys: Iterable[Any]) -> float:
    d = 0.0
    for k in keys:
        d += abs(p.get(k, 0.0) - q.get(k, 0.0))
    return d


@dataclass
class SplitState:
    name: str
    target_frac: float
    n_frames: int = 0

    class_counts: Counter = None
    tod_counts: Counter = None
    density_counts: Counter = None
    area_counts: Counter = None

    group_ids: List[str] = None
    frame_paths: List[str] = None

    def __post_init__(self):
        self.class_counts = Counter()
        self.tod_counts = Counter()
        self.density_counts = Counter()
        self.area_counts = Counter()
        self.group_ids = []
        self.frame_paths = []

    def add_group(self, g: GroupStats):
        self.n_frames += g.n_frames
        self.class_counts.update(g.class_counts)
        self.tod_counts.update(g.tod_counts)
        self.density_counts.update(g.density_counts)
        self.area_counts.update(g.area_counts)
        self.group_ids.append(g.group_id)
        self.frame_paths.extend(g.frame_paths)


def compute_global_targets(groups: List[GroupStats]) -> Dict[str, Any]:
    total_frames = sum(g.n_frames for g in groups)

    global_class = Counter()
    global_tod = Counter()
    global_density = Counter()
    global_area = Counter()

    for g in groups:
        global_class.update(g.class_counts)
        global_tod.update(g.tod_counts)
        global_density.update(g.density_counts)
        global_area.update(g.area_counts)

    targets = {
        "total_frames": total_frames,
        "class_keys": sorted(global_class.keys()),
        "tod_keys": sorted(global_tod.keys()),
        "density_keys": sorted(global_density.keys()),
        "area_keys": sorted(global_area.keys()),
        "class_dist": normalize_counter(global_class),
        "tod_dist": normalize_counter(global_tod),
        "density_dist": normalize_counter(global_density),
        "area_dist": normalize_counter(global_area),
    }
    return targets


def rarity_score(g: GroupStats, global_class_dist: Dict[int, float]) -> float:
    """
    Higher score => assign earlier.
    Use inverse frequency weighting on classes present in the group.
    """
    s = 0.0
    for cls_id, cnt in g.class_counts.items():
        p = global_class_dist.get(cls_id, 1e-12)
        # weight by amount of that class in the group
        s += cnt * (1.0 / max(p, 1e-6))
    # also emphasize very dense groups a bit
    s += 0.25 * g.n_boxes
    return s


def split_groups_greedy(
    groups: Dict[str, GroupStats],
    seed: int,
    train_frac: float,
    val_frac: float,
    test_frac: float,
    weights: Dict[str, float],
) -> Tuple[SplitState, SplitState, SplitState, Dict[str, Any]]:
    """
    Greedy group assignment minimizing distance to global distributions + size penalty.

    weights keys: class, tod, density, area, size
    """
    rnd = random.Random(seed)
    group_list = list(groups.values())

    targets = compute_global_targets(group_list)
    total_frames = targets["total_frames"]

    # Sort groups by rarity (desc), stable tie-break with seed
    rnd.shuffle(group_list)
    group_list.sort(key=lambda g: rarity_score(g, targets["class_dist"]), reverse=True)

    train = SplitState("train", train_frac)
    val = SplitState("val", val_frac)
    test = SplitState("test", test_frac)
    splits = [train, val, test]

    # precompute target frame counts
    target_frames = {
        "train": train_frac * total_frames,
        "val": val_frac * total_frames,
        "test": test_frac * total_frames,
    }

    def score_split(after: SplitState) -> float:
        # distribution distances (L1)
        class_d = l1_dist(normalize_counter(after.class_counts), targets["class_dist"], targets["class_keys"])
        tod_d = l1_dist(normalize_counter(after.tod_counts), targets["tod_dist"], targets["tod_keys"])
        dens_d = l1_dist(normalize_counter(after.density_counts), targets["density_dist"], targets["density_keys"])
        area_d = l1_dist(normalize_counter(after.area_counts), targets["area_dist"], targets["area_keys"])

        # size penalty: keep n_frames close to target
        tf = target_frames[after.name]
        size_d = abs(after.n_frames - tf) / max(tf, 1.0)

        return (
            weights["class"] * class_d +
            weights["tod"] * tod_d +
            weights["density"] * dens_d +
            weights["area"] * area_d +
            weights["size"] * size_d
        )

    # Greedy: for each group, try each split, pick minimal total score across all splits
    for g in group_list:
        best = None
        best_score = float("inf")

        for s in splits:
            # clone minimal stats (cheap-ish since Counters)
            tmp = SplitState(s.name, s.target_frac)
            tmp.n_frames = s.n_frames
            tmp.class_counts = s.class_counts.copy()
            tmp.tod_counts = s.tod_counts.copy()
            tmp.density_counts = s.density_counts.copy()
            tmp.area_counts = s.area_counts.copy()

            tmp.add_group(g)

            # compute global score as sum of each split score
            # (this keeps all splits moving toward their targets)
            total = 0.0
            for other in splits:
                if other.name == s.name:
                    total += score_split(tmp)
                else:
                    total += score_split(other)

            if total < best_score:
                best_score = total
                best = s

        assert best is not None
        best.add_group(g)

    report = {
        "total_frames": total_frames,
        "target_frames": target_frames,
        "actual_frames": {s.name: s.n_frames for s in splits},
    }
    return train, val, test, {**targets, **report}


# -----------------------------
# Reporting + writing
# -----------------------------

def summarize_split(s: SplitState) -> Dict[str, Any]:
    return {
        "n_frames": s.n_frames,
        "n_boxes": int(sum(s.class_counts.values())),
        "n_groups": len(s.group_ids),
        "class_counts": dict(s.class_counts),
        "tod_counts": dict(s.tod_counts),
        "density_counts": dict(s.density_counts),
        "area_counts": dict(s.area_counts),
    }


def write_manifest(out_path: Path, rel_paths: List[str]):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rel_paths = list(rel_paths)
    rel_paths.sort()
    out_path.write_text("\n".join(rel_paths) + ("\n" if rel_paths else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels-root", required=True, type=Path,
                    help="Root of exploded YOLO labels, e.g. data/99_work/yolo_annos_exploded")
    ap.add_argument("--out-dir", required=True, type=Path,
                    help="Output directory for split manifests")
    ap.add_argument("--sites", nargs="*", default=["tankeeah", "kitwanga", "bear"],
                    help="Sites to include (baseline)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train-frac", type=float, default=0.80)
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--test-frac", type=float, default=0.10)
    ap.add_argument("--limit-files", type=int, default=None,
                    help="Debug: limit to N random label files")

    # Objective weights
    ap.add_argument("--w-class", type=float, default=4.0)
    ap.add_argument("--w-tod", type=float, default=1.0)
    ap.add_argument("--w-density", type=float, default=1.0)
    ap.add_argument("--w-area", type=float, default=1.0)
    ap.add_argument("--w-size", type=float, default=2.0)

    args = ap.parse_args()

    if not args.labels_root.exists():
        raise SystemExit(f"labels-root not found: {args.labels_root}")

    ssum = args.train_frac + args.val_frac + args.test_frac
    if abs(ssum - 1.0) > 1e-6:
        raise SystemExit(f"train/val/test fractions must sum to 1.0; got {ssum}")

    sites_keep = set(args.sites) if args.sites else set()

    groups = build_groups(
        labels_root=args.labels_root,
        sites_keep=sites_keep,
        seed=args.seed,
        limit=args.limit_files,
    )

    # Split
    weights = {
        "class": args.w_class,
        "tod": args.w_tod,
        "density": args.w_density,
        "area": args.w_area,
        "size": args.w_size,
    }

    train, val, test, report = split_groups_greedy(
        groups=groups,
        seed=args.seed,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
        test_frac=args.test_frac,
        weights=weights,
    )

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write manifests (relative paths to label files)
    write_manifest(out_dir / "train.txt", train.frame_paths)
    write_manifest(out_dir / "val.txt", val.frame_paths)
    write_manifest(out_dir / "test.txt", test.frame_paths)

    # Group assignment CSV
    with (out_dir / "group_assignments.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group_id", "split", "site", "device", "date", "n_frames", "n_boxes"])
        for s in [train, val, test]:
            for gid in s.group_ids:
                g = groups[gid]
                w.writerow([gid, s.name, g.site, g.device, g.date, g.n_frames, g.n_boxes])

    # JSON report
    full_report = {
        "params": {
            "labels_root": str(args.labels_root),
            "sites": sorted(list(sites_keep)),
            "seed": args.seed,
            "fractions": {"train": args.train_frac, "val": args.val_frac, "test": args.test_frac},
            "weights": weights,
            "grouping": "group_id = site|device|YYYYMMDD",
            "notes": [
                "Split is group-wise to reduce leakage from temporally adjacent frames.",
                "Time-of-day bucket derives from video clip HHMMSS in stem; frames inherit clip bucket.",
                "Balancing is soft; rare classes are prioritized earlier in greedy assignment.",
            ],
        },
        "targets": {
            "total_frames": report["total_frames"],
            "target_frames": report["target_frames"],
            "actual_frames": report["actual_frames"],
            "global_class_dist": report["class_dist"],
            "global_tod_dist": report["tod_dist"],
            "global_density_dist": report["density_dist"],
            "global_area_dist": report["area_dist"],
        },
        "splits": {
            "train": summarize_split(train),
            "val": summarize_split(val),
            "test": summarize_split(test),
        },
    }

    (out_dir / "split_report.json").write_text(json.dumps(full_report, indent=2, sort_keys=True) + "\n")

    print("[make_splits] wrote:")
    print(f"  {out_dir / 'train.txt'} ({len(train.frame_paths)} frames)")
    print(f"  {out_dir / 'val.txt'}   ({len(val.frame_paths)} frames)")
    print(f"  {out_dir / 'test.txt'}  ({len(test.frame_paths)} frames)")
    print(f"  {out_dir / 'group_assignments.csv'}")
    print(f"  {out_dir / 'split_report.json'}")


if __name__ == "__main__":
    main()
