#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml

from object_detection.utils.utils import parse_video_stem


def parse_sites(value: str) -> List[str]:
    return [x for x in re.split(r"[\s,]+", value.strip()) if x]


def read_manifest(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_manifest(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def extract_video_stem(line: str) -> str:
    _, video_stem, _ = extract_split_video_frame(line)
    return video_stem


def extract_site(line: str) -> str:
    video_stem = extract_video_stem(line)
    meta = parse_video_stem(video_stem)
    if meta is None:
        raise ValueError(f"Could not parse video stem: {video_stem}")
    return meta["site"]


def extract_split_video_frame(line: str) -> tuple[str, str, str]:
    """
    Extract:
      split, video_stem, frame_filename

    from either:
      test/VIDEO/frame_000001.jpg

    or:
      /abs/path/.../test/VIDEO/frame_000001.jpg

    This intentionally discards any leading path, including stale
    .dvc/tmp/exps paths.
    """
    p = Path(line)
    parts = p.parts

    for i, part in enumerate(parts[:-2]):
        if part in {"train", "val", "test"}:
            split = parts[i]
            video_stem = parts[i + 1]
            frame_name = parts[i + 2]
            return split, video_stem, frame_name

    raise ValueError(f"Could not extract split/video/frame from manifest line: {line}")


def to_abs_image_path(line: str, source_yolo_workdir: Path) -> str:
    """
    Always rebuild image path under source_yolo_workdir.

    Do NOT preserve absolute input paths because DVC experiments may leave
    stale .dvc/tmp/exps/... paths in manifests.
    """
    split, video_stem, frame_name = extract_split_video_frame(line)
    return str((source_yolo_workdir / split / video_stem / frame_name).resolve())


def rewrite_data_yaml(
    *,
    base_data_yaml: Path,
    output_data_yaml: Path,
    output_test_manifest: Path,
) -> None:
    data: Dict[str, Any] = yaml.safe_load(base_data_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping: {base_data_yaml}")

    data.pop("path", None)

    # Evaluation only needs test, but keeping train/val valid avoids surprises.
    data["train"] = str(output_test_manifest.resolve())
    data["val"] = str(output_test_manifest.resolve())
    data["test"] = str(output_test_manifest.resolve())

    output_data_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_data_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source-yolo-workdir", required=True, type=Path)
    p.add_argument("--source-test-manifest", required=True, type=Path)
    p.add_argument("--source-data-yaml", required=True, type=Path)
    p.add_argument("--out-workdir", required=True, type=Path)
    p.add_argument("--test-sites", required=True, help="Whitespace/comma separated site list")
    args = p.parse_args()

    source_yolo_workdir = args.source_yolo_workdir.resolve()
    out_workdir = args.out_workdir.resolve()
    sites = set(parse_sites(args.test_sites))

    if not sites:
        raise SystemExit("--test-sites produced no sites")

    source_lines = read_manifest(args.source_test_manifest)

    filtered_abs_lines: List[str] = []
    for line in source_lines:
        if extract_site(line) in sites:
            filtered_abs_lines.append(to_abs_image_path(line, source_yolo_workdir))

    output_test_manifest = out_workdir / "test.txt"
    output_data_yaml = out_workdir / "data.yaml"

    write_manifest(output_test_manifest, sorted(filtered_abs_lines))
    rewrite_data_yaml(
        base_data_yaml=args.source_data_yaml,
        output_data_yaml=output_data_yaml,
        output_test_manifest=output_test_manifest,
    )

    print(
        f"Done. sites={sorted(sites)} "
        f"test_images={len(filtered_abs_lines)} "
        f"out_workdir={out_workdir}"
    )


if __name__ == "__main__":
    main()
