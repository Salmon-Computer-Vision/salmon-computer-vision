from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def rewrite_data_yaml_for_workdir(
    input_yaml: Path,
    output_yaml: Path,
    yolo_workdir: Path,
    train_manifest_name: str,
) -> None:
    data: Dict[str, Any] = yaml.safe_load(input_yaml.read_text(encoding="utf-8"))

    data["train"] = str((yolo_workdir / train_manifest_name).resolve())
    data["val"] = str((yolo_workdir / "val.txt").resolve())
    data["test"] = str((yolo_workdir / "test.txt").resolve())

    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_yaml.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
