from __future__ import annotations

import argparse
import json
from pathlib import Path

from object_detection.site_splits.filter import build_site_specific_manifests


def main() -> None:
    p = argparse.ArgumentParser(description="Create site-specific train/val/test manifests")
    p.add_argument("--manifests-root", required=True)
    p.add_argument("--out-root", required=True)
    p.add_argument("--train-sites", nargs="+", required=True)
    p.add_argument("--val-sites", nargs="+", required=True)
    p.add_argument("--test-sites", nargs="+", required=True)
    p.add_argument("--summary-json", default=None)
    args = p.parse_args()

    summary = build_site_specific_manifests(
        manifests_root=Path(args.manifests_root),
        out_root=Path(args.out_root),
        train_sites=args.train_sites,
        val_sites=args.val_sites,
        test_sites=args.test_sites,
    )

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"Done. train={summary['train_count']} "
        f"val={summary['val_count']} "
        f"test={summary['test_count']}"
    )
