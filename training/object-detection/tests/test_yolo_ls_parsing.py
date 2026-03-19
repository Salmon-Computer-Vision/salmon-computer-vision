from pathlib import Path

import pytest

from object_detection.yolo_ls.parsing import (
    coord_mode,
    load_class_map_from_yolo_yaml,
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
