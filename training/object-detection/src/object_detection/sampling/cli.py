from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.sampling.subset import read_manifest, sample_train_subset, write_manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create a smaller training manifest for hyperparameter tuning.")
    p.add_argument("--train-manifest", required=True, help="Path to train.txt")
    p.add_argument("--out-manifest", required=True, help="Path to output train_small.txt")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fraction", type=float, default=None, help="Fraction of train set to keep, e.g. 0.1")
    p.add_argument("--num-samples", type=int, default=None, help="Exact number of samples to keep")
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

    print(
        f"Done. input={len(relpaths)} "
        f"output={len(sampled)} "
        f"out_manifest={out_manifest}"
    )
