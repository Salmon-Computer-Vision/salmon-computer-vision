import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterable, Any
from collections import Counter

from object_detection.splits.parsing import (
        parse_video_stem,
        time_bucket,
        density_bin,
        parse_frame_idx,
        read_yolo_label,
)

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
    ar_counts: Counter

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

def build_groups(
    labels_root: Path,
    sites_keep: List[str],
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

        n_boxes, class_counts, area_counts, ar_counts = read_yolo_label(f)
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
                ar_counts=Counter(),
                frame_paths=[],
            )

        g = groups[group_id]
        g.n_frames += 1
        g.n_boxes += n_boxes
        g.class_counts.update(class_counts)
        g.tod_counts[tod] += 1
        g.density_counts[dens_bin] += 1
        g.area_counts.update(area_counts)
        g.ar_counts.update(ar_counts)
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
    ar_counts: Counter = None

    group_ids: List[str] = None
    frame_paths: List[str] = None

    def __post_init__(self):
        self.class_counts = Counter()
        self.tod_counts = Counter()
        self.density_counts = Counter()
        self.area_counts = Counter()
        self.ar_counts = Counter()
        self.group_ids = []
        self.frame_paths = []

    def add_group(self, g: GroupStats):
        self.n_frames += g.n_frames
        self.class_counts.update(g.class_counts)
        self.tod_counts.update(g.tod_counts)
        self.density_counts.update(g.density_counts)
        self.area_counts.update(g.area_counts)
        self.ar_counts.update(g.ar_counts)
        self.group_ids.append(g.group_id)
        self.frame_paths.extend(g.frame_paths)


def compute_global_targets(groups: List[GroupStats]) -> Dict[str, Any]:
    total_frames = sum(g.n_frames for g in groups)

    global_class = Counter()
    global_tod = Counter()
    global_density = Counter()
    global_area = Counter()
    global_ar = Counter()

    for g in groups:
        global_class.update(g.class_counts)
        global_tod.update(g.tod_counts)
        global_density.update(g.density_counts)
        global_area.update(g.area_counts)
        global_ar.update(g.ar_counts)

    targets = {
        "total_frames": total_frames,
        "class_keys": sorted(global_class.keys()),
        "tod_keys": sorted(global_tod.keys()),
        "density_keys": sorted(global_density.keys()),
        "area_keys": sorted(global_area.keys()),
        "ar_keys": sorted(global_ar.keys()),
        "class_dist": normalize_counter(global_class),
        "tod_dist": normalize_counter(global_tod),
        "density_dist": normalize_counter(global_density),
        "area_dist": normalize_counter(global_area),
        "ar_dist": normalize_counter(global_ar),
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
    splits = [test, val, train]

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
        ar_d = l1_dist(normalize_counter(after.ar_counts), targets["ar_dist"], targets["ar_keys"])

        # size penalty: keep n_frames close to target
        tf = target_frames[after.name]
        size_d = abs(after.n_frames - tf) / max(tf, 1.0)

        return (
            weights["class"] * class_d +
            weights["tod"] * tod_d +
            weights["density"] * dens_d +
            weights["area"] * area_d +
            weights["ar"] * ar_d +
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
        "ar_counts": dict(s.ar_counts),
    }


def write_manifest(out_path: Path, rel_paths: List[str]):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rel_paths = list(rel_paths)
    rel_paths.sort()
    out_path.write_text("\n".join(rel_paths) + ("\n" if rel_paths else ""))

