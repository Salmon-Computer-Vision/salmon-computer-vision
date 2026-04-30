from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.analysis.plots import plot_site_class_stats


def main() -> None:
    p = argparse.ArgumentParser(description="Plot site/class annotation statistics")
    p.add_argument("--stats-dir", required=True, help="Directory containing CSV stats from YOLO conversion")
    p.add_argument("--out-dir", required=True, help="Directory to write PNG plots")
    args = p.parse_args()

    outputs = plot_site_class_stats(
        stats_dir=Path(args.stats_dir),
        out_dir=Path(args.out_dir),
    )

    print("Wrote plots:")
    for out in outputs:
        print(f"  {out}")
