from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.sampling.subset import (
    read_manifest, 
    sample_train_subset, 
    write_manifest,
    write_small_data_yaml,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create a smaller training manifest for hyperparameter tuning.")
    p.add_argument("--train-manifest", required=True, help="Path to train.txt")
    p.add_argument("--out-manifest", required=True, help="Path to output train_small.txt")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fraction", type=float, default=None, help="Fraction of train set to keep, e.g. 0.1")
    p.add_argument("--num-samples", type=int, default=None, help="Exact number of samples to keep")
    p.add_argument("--base-data-yaml", default=None, help="Existing data.yaml to copy and modify")
    p.add_argument("--out-data-yaml", default=None, help="Output data_small.yaml")
    p.add_argument(
        "--no-preserve-site-proportions",
        action="store_true",
        help="Use plain random sampling instead of preserving site proportions",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    train_manifest = Path(args.train_manifest)
    out_manifest = Path(args.out_manifest)

    relpaths = read_manifest(train_manifest)
    sampled = sample_train_subset(
        relpaths,
        seed=args.seed,
        fraction=args.fraction,
        num_samples=args.num_samples,
        preserve_site_proportions=not args.no_preserve_site_proportions,
    )
    write_manifest(out_manifest, sampled)

    if args.base_data_yaml or args.out_data_yaml:
        if not args.base_data_yaml or not args.out_data_yaml:
            raise ValueError("Both --base-data-yaml and --out-data-yaml must be provided together")
        write_small_data_yaml(
            base_data_yaml=Path(args.base_data_yaml),
            out_data_yaml=Path(args.out_data_yaml),
        )

    print(
        f"Done. input={len(relpaths)} "
        f"output={len(sampled)} "
        f"out_manifest={out_manifest}"
    )
