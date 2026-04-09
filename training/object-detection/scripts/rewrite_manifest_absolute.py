#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.training.manifests import rewrite_manifest_to_absolute


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-manifest", required=True)
    p.add_argument("--output-manifest", required=True)
    p.add_argument("--dataset-root", required=True)
    args = p.parse_args()

    rewrite_manifest_to_absolute(
        input_manifest=Path(args.input_manifest),
        output_manifest=Path(args.output_manifest),
        dataset_root=Path(args.dataset_root),
    )


if __name__ == "__main__":
    main()
