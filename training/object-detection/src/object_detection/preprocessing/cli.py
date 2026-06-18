from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.preprocessing.crop_sites import crop_sites_top_half


def main() -> None:
    p = argparse.ArgumentParser(description="Crop selected site frames and rewrite YOLO labels.")
    p.add_argument("--dataset-root", required=True, type=Path)
    p.add_argument("--sites", nargs="+", required=True)
    p.add_argument("--crop", choices=["top_half"], default="top_half")
    p.add_argument("--splits", nargs="*", default=["train", "val", "test"])
    p.add_argument(
        "--min-visible-frac",
        type=float,
        default=0.05,
        help="Drop boxes whose visible area after cropping is below this fraction.",
    )
    p.add_argument("--summary-json", default=None, type=Path)
    args = p.parse_args()

    if args.crop != "top_half":
        raise SystemExit(f"Unsupported crop: {args.crop}")

    summary = crop_sites_top_half(
        dataset_root=args.dataset_root,
        sites=args.sites,
        split_names=args.splits,
        min_visible_frac=args.min_visible_frac,
        summary_json=args.summary_json,
    )

    print(
        "Done. "
        f"images_seen={summary.images_seen} "
        f"images_cropped={summary.images_cropped} "
        f"labels_rewritten={summary.labels_rewritten} "
        f"boxes_before={summary.label_lines_before} "
        f"boxes_after={summary.label_lines_after} "
        f"boxes_dropped={summary.boxes_dropped} "
        f"images_failed={summary.images_failed}"
    )
