#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.training.data_yaml import rewrite_data_yaml_for_workdir


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-yaml", required=True)
    p.add_argument("--output-yaml", required=True)
    p.add_argument("--yolo-workdir", required=True)
    p.add_argument("--train-manifest-name", required=True)
    args = p.parse_args()

    rewrite_data_yaml_for_workdir(
        input_yaml=Path(args.input_yaml),
        output_yaml=Path(args.output_yaml),
        yolo_workdir=Path(args.yolo_workdir),
        train_manifest_name=args.train_manifest_name,
    )


if __name__ == "__main__":
    main()
