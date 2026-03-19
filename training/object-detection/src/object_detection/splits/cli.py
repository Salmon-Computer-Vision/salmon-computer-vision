import argparse
import csv
import json
from pathlib import Path

from object_detection.splits.splitter import (
        build_groups,
        split_groups_greedy,
        write_manifest,
        summarize_split,
)

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
    ap.add_argument("--w-ar", type=float, default=1.0)
    ap.add_argument("--w-size", type=float, default=2.0)

    args = ap.parse_args()

    if not args.labels_root.exists():
        raise SystemExit(f"labels-root not found: {args.labels_root}")

    ssum = args.train_frac + args.val_frac + args.test_frac
    if abs(ssum - 1.0) > 1e-6:
        raise SystemExit(f"train/val/test fractions must sum to 1.0; got {ssum}")

    groups = build_groups(
        labels_root=args.labels_root,
        sites_keep=args.sites,
        seed=args.seed,
        limit=args.limit_files,
    )

    # Split
    weights = {
        "class": args.w_class,
        "tod": args.w_tod,
        "density": args.w_density,
        "area": args.w_area,
        "ar": args.w_ar,
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
            "sites": args.sites,
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
            "global_ar_dist": report["ar_dist"],
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


