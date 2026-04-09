from __future__ import annotations

from pathlib import Path
from typing import List


def read_manifest(path: Path) -> List[str]:
    lines: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            lines.append(s)
    return lines


def write_manifest(path: Path, relpaths: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(relpaths) + ("\n" if relpaths else ""), encoding="utf-8")


def rewrite_manifest_to_absolute(
    input_manifest: Path,
    output_manifest: Path,
    dataset_root: Path,
) -> None:
    """
    Convert manifest entries like:
      train/.../frame_000123.jpg
    into:
      /abs/path/to/yolo_workdir/train/.../frame_000123.jpg
    """
    abs_lines: List[str] = []
    for line in read_manifest(input_manifest):
        abs_lines.append(str((dataset_root / line).resolve()))
    write_manifest(output_manifest, abs_lines)
