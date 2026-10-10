#!/usr/bin/env python3
"""Aggregate DVC per-site YOLO annotation statistics for reproducible plots.

The converter writes site-specific CSVs. In particular, a within-class percent
in a *single* site's stats cannot be compared across sites. This script joins
site/class counts and recomputes both percentage columns over the selected set.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import yaml


KIND_SPECS = {
    "frame": (
        "site_class_frame_counts.csv", "frame_count", "frame_pct_within_class", "frame_pct_within_site"
    ),
    "box": (
        "site_class_box_counts.csv", "box_count", "box_pct_within_class", "box_pct_within_site"
    ),
}


def read_site_names(params_yaml: Path) -> list[str]:
    with params_yaml.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    sites = (data or {}).get("data", {}).get("sites")
    if not isinstance(sites, list) or not sites or not all(isinstance(s, str) and s.strip() for s in sites):
        raise ValueError("params.yaml: data.sites must be a nonempty list of site names")
    if len(sites) != len(set(sites)):
        raise ValueError("params.yaml: data.sites contains duplicates")
    return sites


def read_counts(input_root: Path, sites: list[str], kind: str) -> tuple[dict[tuple[str, int], int], dict[int, str]]:
    filename, count_col, *_ = KIND_SPECS[kind]
    site_class: dict[tuple[str, int], int] = {}
    class_names: dict[int, str] = {}
    for site in sites:
        path = input_root / site / "yolo_annos_stats" / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}. Run dvc repro build_model_input@{site} first.")
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {"site", "class_id", "class_name", count_col}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"{path}: missing columns {sorted(required - set(reader.fieldnames or []))}")
            for row in reader:
                if row["site"] != site:
                    raise ValueError(f"{path}: CSV site {row['site']!r} does not match expected {site!r}")
                try:
                    class_id = int(row["class_id"])
                    raw = row[count_col].strip()
                    count = int(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{path}: invalid {count_col} or class_id in {row!r}") from exc
                if count < 0:
                    raise ValueError(f"{path}: negative {count_col}: {count}")
                name = row["class_name"].strip()
                if not name:
                    raise ValueError(f"{path}: empty class_name for class_id {class_id}")
                previous_name = class_names.setdefault(class_id, name)
                if previous_name != name:
                    raise ValueError(f"Class {class_id} maps to both {previous_name!r} and {name!r}; check config/salmon_yolo.yaml")
                key = (site, class_id)
                if key in site_class:
                    raise ValueError(f"{path}: duplicate site/class_id row {key}")
                site_class[key] = count
        if not any(s == site for s, _ in site_class):
            raise ValueError(f"{path}: no site/class rows; cannot determine zero-count classes")
    return site_class, class_names


def aggregate_kind(input_root: Path, sites: list[str], out_dir: Path, kind: str) -> Path:
    filename, count_col, pct_class_col, pct_site_col = KIND_SPECS[kind]
    counts, classes = read_counts(input_root, sites, kind)
    by_class: dict[int, int] = defaultdict(int)
    by_site: dict[str, int] = defaultdict(int)
    for (site, class_id), count in counts.items():
        by_class[class_id] += count
        by_site[site] += count
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / filename
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["site", "class_id", "class_name", count_col, pct_class_col, pct_site_col])
        writer.writeheader()
        for site in sites:
            for class_id in sorted(classes):
                count = counts.get((site, class_id), 0)
                writer.writerow({
                    "site": site,
                    "class_id": class_id,
                    "class_name": classes[class_id],
                    count_col: count,
                    pct_class_col: round(100 * count / by_class[class_id], 6) if by_class[class_id] else 0.0,
                    pct_site_col: round(100 * count / by_site[site], 6) if by_site[site] else 0.0,
                })
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params-yaml", type=Path, default=Path("params.yaml"))
    parser.add_argument("--sites-root", type=Path, default=Path("data/02_interim/sites"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    sites = read_site_names(args.params_yaml)
    for kind in KIND_SPECS:
        output = aggregate_kind(args.sites_root, sites, args.out_dir, kind)
        print(f"Wrote {output} ({len(sites)} sites)")


if __name__ == "__main__":
    main()
