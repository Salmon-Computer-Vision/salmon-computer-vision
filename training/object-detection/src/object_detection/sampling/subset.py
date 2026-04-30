from __future__ import annotations

import math
import yaml
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from object_detection.utils.utils import parse_video_stem


def read_manifest(path: Path) -> List[str]:
    lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines


def write_manifest(path: Path, relpaths: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    relpaths = sorted(relpaths)
    path.write_text("\n".join(relpaths) + ("\n" if relpaths else ""), encoding="utf-8")


def write_small_data_yaml(
    base_data_yaml: Path,
    out_data_yaml: Path,
) -> None:
    data: Dict[str, Any] = yaml.safe_load(base_data_yaml.read_text(encoding="utf-8"))

    data["train"] = "train_small.txt"

    out_data_yaml.parent.mkdir(parents=True, exist_ok=True)
    out_data_yaml.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )


def extract_video_stem_from_image_relpath(relpath: str) -> str:
    """
    Example:
      train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.jpg
    -> HIRMD-tankeeah-jetson-0_20250714_012827_M
    """
    p = Path(relpath.strip())
    if len(p.parts) < 3:
        raise ValueError("Invalid image relpath: %s" % relpath)
    return p.parts[1]


def extract_site_from_image_relpath(relpath: str) -> str:
    video_stem = extract_video_stem_from_image_relpath(relpath)
    meta = parse_video_stem(video_stem)
    if meta is None:
        return "unknown"
    return meta["site"]


def choose_target_count(total: int, fraction: Optional[float], num_samples: Optional[int]) -> int:
    if fraction is None and num_samples is None:
        raise ValueError("One of fraction or num_samples must be provided")
    if fraction is not None and num_samples is not None:
        raise ValueError("Provide only one of fraction or num_samples")

    if fraction is not None:
        if fraction <= 0 or fraction > 1:
            raise ValueError("fraction must be in (0, 1]")
        return max(1, int(math.floor(total * fraction)))

    assert num_samples is not None
    if num_samples <= 0:
        raise ValueError("num_samples must be > 0")
    return min(total, num_samples)


def allocate_counts_proportionally(
    groups: Dict[str, List[str]],
    target_total: int,
) -> Dict[str, int]:
    """
    Largest-remainder allocation preserving group proportions.
    """
    total = sum(len(v) for v in groups.values())
    if total == 0:
        return {k: 0 for k in groups}

    base: Dict[str, int] = {}
    remainders: List[Tuple[float, str]] = []

    assigned = 0
    for key, items in groups.items():
        exact = target_total * (len(items) / float(total))
        take = int(math.floor(exact))
        take = min(take, len(items))
        base[key] = take
        assigned += take
        remainders.append((exact - take, key))

    remaining = target_total - assigned
    remainders.sort(reverse=True)

    for _, key in remainders:
        if remaining <= 0:
            break
        if base[key] < len(groups[key]):
            base[key] += 1
            remaining -= 1

    return base


def sample_train_subset(
    train_relpaths: Sequence[str],
    *,
    seed: int = 42,
    fraction: Optional[float] = None,
    num_samples: Optional[int] = None,
    preserve_site_proportions: bool = True,
) -> List[str]:
    total = len(train_relpaths)
    if total == 0:
        return []

    target_total = choose_target_count(total, fraction, num_samples)
    rng = random.Random(seed)

    relpaths = list(train_relpaths)

    if not preserve_site_proportions:
        rng.shuffle(relpaths)
        return sorted(relpaths[:target_total])

    by_site: Dict[str, List[str]] = defaultdict(list)
    for relpath in relpaths:
        by_site[extract_site_from_image_relpath(relpath)].append(relpath)

    for site in by_site:
        rng.shuffle(by_site[site])

    site_targets = allocate_counts_proportionally(by_site, target_total)

    sampled: List[str] = []
    for site, items in by_site.items():
        sampled.extend(items[:site_targets[site]])

    # Safety in case rounding/caps left us short
    if len(sampled) < target_total:
        used = set(sampled)
        leftovers = [p for p in relpaths if p not in used]
        rng.shuffle(leftovers)
        sampled.extend(leftovers[: target_total - len(sampled)])

    return sorted(sampled[:target_total])
