from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

import yaml

from object_detection.utils.utils import parse_video_stem


def read_manifest(path: Path) -> List[str]:
    lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines


def write_manifest(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = sorted(lines)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def extract_video_stem_from_manifest_line(line: str) -> str:
    """
    Handles lines like:
      train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.jpg
    or absolute paths ending with the same structure.
    """
    p = Path(line)
    parts = p.parts

    # Find ".../<split>/<video_stem>/<frame>.jpg"
    for i in range(len(parts) - 2):
        if parts[i] in {"train", "val", "test"}:
            return parts[i + 1]

    raise ValueError(f"Could not extract video stem from manifest line: {line}")


def extract_site_from_manifest_line(line: str) -> str:
    video_stem = extract_video_stem_from_manifest_line(line)
    meta = parse_video_stem(video_stem)
    if meta is None:
        raise ValueError(f"Could not parse video stem: {video_stem}")
    return meta["site"]


def filter_manifest_by_sites(lines: Sequence[str], allowed_sites: Iterable[str]) -> List[str]:
    allowed: Set[str] = set(allowed_sites)
    return [line for line in lines if extract_site_from_manifest_line(line) in allowed]


def rewrite_data_yaml(
    base_data_yaml: Path,
    out_data_yaml: Path,
    train_manifest: Path,
    val_manifest: Path,
    test_manifest: Path,
) -> None:
    data = yaml.safe_load(base_data_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML: {base_data_yaml}")

    data.pop("path", None)
    data["train"] = 'train.txt'
    data["val"] = 'val.txt'
    data["test"] = 'test.txt'

    out_data_yaml.parent.mkdir(parents=True, exist_ok=True)
    out_data_yaml.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )


def build_site_specific_manifests(
    *,
    manifests_root: Path,
    out_root: Path,
    train_sites: Sequence[str],
    val_sites: Sequence[str],
    test_sites: Sequence[str],
) -> Dict[str, int]:
    train_in = manifests_root / "train.txt"
    val_in = manifests_root / "val.txt"
    test_in = manifests_root / "test.txt"
    data_yaml_in = manifests_root / "data.yaml"

    train_out = out_root / "train.txt"
    val_out = out_root / "val.txt"
    test_out = out_root / "test.txt"
    data_yaml_out = out_root / "data.yaml"

    train_lines = read_manifest(train_in)
    val_lines = read_manifest(val_in)
    test_lines = read_manifest(test_in)

    train_filtered = filter_manifest_by_sites(train_lines, train_sites)
    val_filtered = filter_manifest_by_sites(val_lines, val_sites)
    test_filtered = filter_manifest_by_sites(test_lines, test_sites)

    write_manifest(train_out, train_filtered)
    write_manifest(val_out, val_filtered)
    write_manifest(test_out, test_filtered)

    rewrite_data_yaml(
        base_data_yaml=data_yaml_in,
        out_data_yaml=data_yaml_out,
        train_manifest=train_out,
        val_manifest=val_out,
        test_manifest=test_out,
    )

    return {
        "train_count": len(train_filtered),
        "val_count": len(val_filtered),
        "test_count": len(test_filtered),
    }
