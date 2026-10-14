import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterable, Any
from collections import Counter

from object_detection.splits.parsing import (
        time_bucket,
        density_bin,
        parse_frame_idx,
        read_yolo_label,
)
from object_detection.utils.utils import parse_video_stem

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
    # Video-level aggregates let the fallback reassign *complete videos* without
    # re-reading hundreds of thousands of YOLO frame labels.
    video_stats: Dict[str, "GroupStats"] = field(default_factory=dict)


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

        v = g.video_stats.get(video_stem)
        if v is None:
            v = GroupStats(
                group_id=video_stem, site=site, device=meta["device"],
                date=meta["date"], n_frames=0, n_boxes=0,
                class_counts=Counter(), tod_counts=Counter(),
                density_counts=Counter(), area_counts=Counter(),
                ar_counts=Counter(), frame_paths=[],
            )
            g.video_stats[video_stem] = v
        v.n_frames += 1
        v.n_boxes += n_boxes
        v.class_counts.update(class_counts)
        v.tod_counts[tod] += 1
        v.density_counts[dens_bin] += 1
        v.area_counts.update(area_counts)
        v.ar_counts.update(ar_counts)
        v.frame_paths.append(rel_path)

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



# -----------------------------
# Minimum video coverage / sparse-day fallback
# -----------------------------

def enforce_minimum_video_splits(
    groups: Dict[str, GroupStats],
    train: SplitState,
    val: SplitState,
    test: SplitState,
    *,
    seed: int,
    train_frac: float,
    val_frac: float,
    test_frac: float,
    min_val_videos: int = 2,
    min_test_videos: int = 2,
) -> Tuple[SplitState, SplitState, SplitState, Dict[str, str], Dict[str, Any]]:
    """Guarantee complete-video holdouts when at least three videos exist.

    Prefer moving whole site/device/day groups. If that cannot populate all
    partitions, assign chronological *blocks of videos* from opposite ends of
    the timeline; never divide a video's frame labels across splits.

    On small datasets where two holdout videos each would leave no train videos,
    lower both holdout minima to 1 and record the adjustment. With fewer than
    three videos, fail loudly rather than silently writing empty holdouts.
    """
    if min_val_videos < 0 or min_test_videos < 0:
        raise ValueError("Minimum video counts must be non-negative")
    if not (0 < train_frac <= 1 and 0 <= val_frac < 1 and 0 <= test_frac < 1):
        raise ValueError("Invalid split fractions")
    if any(not g.video_stats for g in groups.values()):
        raise ValueError("Missing video_stats: build groups using build_groups()")

    videos: Dict[str, GroupStats] = {}
    parent: Dict[str, str] = {}
    for group_id, group in sorted(groups.items()):
        for stem, v in group.video_stats.items():
            if stem in videos:
                raise ValueError(f"Video in multiple source groups: {stem}")
            videos[stem], parent[stem] = v, group_id
    total_videos = len(videos)
    if total_videos < 3:
        raise ValueError(
            f"Only {total_videos} distinct video(s) with labels found; need at "
            "least 3 to keep nonempty train/val/test without splitting videos."
        )

    requested = {"val": min_val_videos, "test": min_test_videos, "train": 1}
    if total_videos >= min_val_videos + min_test_videos + 1:
        effective = requested.copy()
    else:
        # If requested two-video holdouts are impossible, favor one video in
        # each evaluation split plus at least one independent training video.
        effective = {"train": 1, "val": int(val_frac > 0 and min_val_videos > 0),
                     "test": int(test_frac > 0 and min_test_videos > 0)}
    if sum(effective.values()) > total_videos:
        raise ValueError("Requested minimum split sizes exceed available videos")

    assign: Dict[str, str] = {}
    for state in (train, val, test):
        for gid in state.group_ids:
            for stem in groups[gid].video_stats:
                if stem in assign:
                    raise ValueError(f"Duplicate group assignment for video {stem}")
                assign[stem] = state.name
    if set(assign) != set(videos):
        raise ValueError("Greedy split failed to assign every video exactly once")

    def counts():
        return {name: sum(1 for a in assign.values() if a == name)
                for name in ("train", "val", "test")}

    def valid():
        c = counts()
        return all(c[name] >= minimum for name, minimum in effective.items())

    mode = "day_groups"
    # First repair the greedy assignment using whole groups only, preserving
    # temporal isolation. No such repair is possible for fewer than 3 groups.
    if not valid() and len(groups) >= 3:
        for destination in ("train", "val", "test"):
            while counts()[destination] < effective[destination]:
                current = counts()
                choices = []
                for gid, group in groups.items():
                    current_splits = {assign[stem] for stem in group.video_stats}
                    if len(current_splits) != 1:
                        continue
                    donor = next(iter(current_splits))
                    if donor == destination:
                        continue
                    n = len(group.video_stats)
                    if current[donor] - n < effective[donor]:
                        continue
                    desired = {"train": train_frac, "val": val_frac,
                               "test": test_frac}[destination]
                    target = desired * sum(v.n_frames for v in videos.values())
                    have = sum(v.n_frames for stem, v in videos.items()
                               if assign[stem] == destination)
                    choices.append((abs(target - (have + group.n_frames)),
                                    group.n_frames, gid, group))
                if not choices:
                    break
                _, _, _, selected = min(choices, key=lambda x: x[:3])
                for stem in selected.video_stats:
                    assign[stem] = destination
        if valid():
            mode = "repaired_day_groups"

    if not valid():
        # Exact group isolation is infeasible (or the greedily assigned groups
        # could not be moved). Use deterministic, consecutive *video* blocks.
        # Separating earliest from latest provides less temporal interleaving
        # than uniformly random video assignments from the same day.
        mode = "temporal_video_blocks"
        order = sorted(videos, key=lambda stem: (
            videos[stem].date, videos[stem].site, videos[stem].device,
            stem.split("_")[2] if stem.count("_") >= 2 else stem,
            stem,
        ))
        assign = {stem: "train" for stem in videos}
        available = list(order)
        targets = {
            "val": val_frac * sum(v.n_frames for v in videos.values()),
            "test": test_frac * sum(v.n_frames for v in videos.values()),
        }
        # Reserve the other evaluation split's minimum and one train video.
        for destination, from_left, reserve in (
            ("val", True, effective["test"] + effective["train"]),
            ("test", False, effective["train"]),
        ):
            selected_frames = 0
            selected_n = 0
            while len(available) > reserve and (
                selected_n < effective[destination]
                or selected_frames < targets[destination]
            ):
                stem = available.pop(0 if from_left else -1)
                assign[stem] = destination
                selected_frames += videos[stem].n_frames
                selected_n += 1

    if not valid():
        raise RuntimeError(f"Could not satisfy video minima: {counts()} < {effective}")

    # Rebuild counters at video granularity for a correct report even when a
    # source day is shared across splits. Restore original group IDs in states.
    results = {}
    for name, fraction in (("train", train_frac), ("val", val_frac), ("test", test_frac)):
        state = SplitState(name, fraction)
        included = sorted(stem for stem, assigned in assign.items() if assigned == name)
        for stem in included:
            state.add_group(videos[stem])
        state.group_ids = sorted({parent[stem] for stem in included})
        results[name] = state

    split_by_group = {}
    for stem, dest in assign.items():
        split_by_group.setdefault(parent[stem], set()).add(dest)
    broken = sorted(gid for gid, splits in split_by_group.items() if len(splits) > 1)
    details = {
        "strategy": mode,
        "total_videos": total_videos,
        "requested_min_videos": requested,
        "effective_min_videos": effective,
        "minimums_reduced": requested != effective,
        "actual_videos": counts(),
        "groups_shared_across_splits": broken,
        "n_groups_shared_across_splits": len(broken),
        "note": (
            "Video-block fallback breaks site/device/day isolation but never "
            "divides a video; temporal leakage between neighboring clips is "
            "possible. Consider independent days for final test reporting."
            if broken else "All site/device/day groups remain isolated."
        ),
    }
    return results["train"], results["val"], results["test"], assign, details
