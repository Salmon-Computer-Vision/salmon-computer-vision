import json
from pathlib import Path

import pytest

from object_detection.yolo_ls.parsing import (
    coord_mode,
    load_class_map_from_yolo_yaml,
    load_json_paths_from_site_manifest,
    to_yolo,
)


def test_load_class_map_from_yolo_yaml_dict(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text("names:\n  0: Coho\n  1: Sockeye\n", encoding="utf-8")

    got = load_class_map_from_yolo_yaml(yaml_path)
    assert got == {"Coho": 0, "Sockeye": 1}


def test_load_class_map_from_yolo_yaml_list(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text("names: [Coho, Sockeye]\n", encoding="utf-8")

    got = load_class_map_from_yolo_yaml(yaml_path)
    assert got == {"Coho": 0, "Sockeye": 1}


def test_load_class_map_from_yolo_yaml_missing_names(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text("train: images/train\n", encoding="utf-8")

    with pytest.raises(ValueError, match="'names' not found"):
        load_class_map_from_yolo_yaml(yaml_path)


def test_load_class_map_from_yolo_yaml_bad_type(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text("names: 123\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported 'names' structure"):
        load_class_map_from_yolo_yaml(yaml_path)



def test_coord_mode_normalized():
    assert coord_mode(0.1, 0.2, 0.3, 0.4) == "normalized"


def test_coord_mode_percent():
    assert coord_mode(10, 20, 30, 40) == "percent"


def test_coord_mode_pixel():
    assert coord_mode(120, 20, 30, 40) == "pixel"


def test_to_yolo_percent():
    xc, yc, w, h = to_yolo(10, 20, 30, 40, vid_w=1280, vid_h=720, forced_mode="percent")
    assert xc == pytest.approx(0.25)
    assert yc == pytest.approx(0.40)
    assert w == pytest.approx(0.30)
    assert h == pytest.approx(0.40)


def test_to_yolo_pixel():
    xc, yc, w, h = to_yolo(64, 36, 128, 72, vid_w=1280, vid_h=720, forced_mode="pixel")
    assert xc == pytest.approx((64 + 64) / 1280)
    assert yc == pytest.approx((36 + 36) / 720)
    assert w == pytest.approx(128 / 1280)
    assert h == pytest.approx(72 / 720)


def test_to_yolo_auto():
    xc, yc, w, h = to_yolo(10, 20, 30, 40, vid_w=1280, vid_h=720, forced_mode="auto")
    assert xc == pytest.approx(0.25)
    assert yc == pytest.approx(0.40)
    assert w == pytest.approx(0.30)
    assert h == pytest.approx(0.40)


def test_to_yolo_clamps():
    xc, yc, w, h = to_yolo(-10, -10, 200, 200, vid_w=100, vid_h=100, forced_mode="pixel")
    assert 0.0 <= xc <= 1.0
    assert 0.0 <= yc <= 1.0
    assert 0.0 <= w <= 1.0
    assert 0.0 <= h <= 1.0


def test_to_yolo_invalid_mode():
    with pytest.raises(ValueError, match="Unknown coord_mode"):
        to_yolo(1, 2, 3, 4, vid_w=100, vid_h=100, forced_mode="bad_mode")



def test_load_json_paths_from_site_manifest_resolves_deduplicates_and_sorts(
    tmp_path: Path,
):
    raw_root = tmp_path / "raw"
    a = raw_root / "a.json"
    b = raw_root / "nested" / "b.json"

    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)

    a.write_text("[]", encoding="utf-8")
    b.write_text("[]", encoding="utf-8")

    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "site": "tankeeah",
                "raw_root": str(raw_root),
                "files": [
                    {"path": "nested/b.json"},
                    {"path": "a.json"},
                    {"path": "nested/b.json"},
                ],
            }
        ),
        encoding="utf-8",
    )

    got = load_json_paths_from_site_manifest(manifest_path)

    assert got == sorted([a, b])


def test_load_json_paths_from_site_manifest_raw_root_override(tmp_path: Path):
    actual_root = tmp_path / "actual"
    actual_root.mkdir()

    json_path = actual_root / "project.json"
    json_path.write_text("[]", encoding="utf-8")

    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": "/old/machine/path",
                "files": [{"path": "project.json"}],
            }
        ),
        encoding="utf-8",
    )

    got = load_json_paths_from_site_manifest(
        manifest_path,
        raw_root_override=actual_root,
    )

    assert got == [json_path]


def test_load_json_paths_from_site_manifest_absolute_path(tmp_path: Path):
    json_path = tmp_path / "absolute.json"
    json_path.write_text("[]", encoding="utf-8")

    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": "/unused",
                "files": [{"path": str(json_path)}],
            }
        ),
        encoding="utf-8",
    )

    assert load_json_paths_from_site_manifest(manifest_path) == [json_path]


def test_load_json_paths_from_site_manifest_invalid_json(tmp_path: Path):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not read site manifest"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_requires_object(tmp_path: Path):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text("[]", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Site manifest must contain a JSON object",
    ):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_requires_files_list(tmp_path: Path):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps({"raw_root": str(tmp_path), "files": "a.json"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain a 'files' list"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_requires_raw_root_without_override(
    tmp_path: Path,
):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps({"files": [{"path": "a.json"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has no 'raw_root'"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_rejects_non_object_file_entry(
    tmp_path: Path,
):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": str(tmp_path),
                "files": ["a.json"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid files\[0\] entry"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_requires_file_path(tmp_path: Path):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": str(tmp_path),
                "files": [{"sha256": "abc"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Missing path in files\[0\]"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_missing_referenced_file(
    tmp_path: Path,
):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": str(tmp_path),
                "files": [{"path": "missing.json"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        FileNotFoundError,
        match="JSON referenced by .* does not exist",
    ):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_rejects_directory_target(
    tmp_path: Path,
):
    target_dir = tmp_path / "not_a_file"
    target_dir.mkdir()

    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": str(tmp_path),
                "files": [{"path": target_dir.name}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is not a file"):
        load_json_paths_from_site_manifest(manifest_path)


def test_load_json_paths_from_site_manifest_rejects_empty_file_list(
    tmp_path: Path,
):
    manifest_path = tmp_path / "site.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_root": str(tmp_path),
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contains no JSON files"):
        load_json_paths_from_site_manifest(manifest_path)
