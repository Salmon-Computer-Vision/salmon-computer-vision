from collections import Counter

from object_detection.splits.parsing import (
    ar_bin,
    area_bin,
    density_bin,
    parse_frame_idx,
    parse_video_stem,
    read_yolo_label,
    time_bucket,
)


def test_parse_video_stem_happy_path():
    got = parse_video_stem("HIRMD-tankeeah-jetson-0_20250714_012827_M")
    assert got == {
        "org": "HIRMD",
        "site": "tankeeah",
        "device": "jetson-0",
        "date": "20250714",
        "time": "012827",
    }


def test_parse_video_stem_invalid():
    assert parse_video_stem("not_a_valid_stem") is None


def test_time_bucket():
    assert time_bucket("010203") == "night"
    assert time_bucket("070000") == "morning"
    assert time_bucket("130000") == "afternoon"
    assert time_bucket("200000") == "evening"
    assert time_bucket("bad") == "unknown"


def test_density_bin():
    assert density_bin(0) == "0"
    assert density_bin(1) == "1"
    assert density_bin(2) == "2"
    assert density_bin(4) == "3-4"
    assert density_bin(7) == "5-9"
    assert density_bin(10) == "10+"


def test_ar_bin():
    assert ar_bin(0.1, 0.3) == "tall"
    assert ar_bin(0.3, 0.3) == "square"
    assert ar_bin(0.5, 0.2) == "wide"
    assert ar_bin(0.0, 0.2) == "invalid"


def test_area_bin():
    assert area_bin(0) == "0"
    assert area_bin(0.001) == "<0.0025"
    assert area_bin(0.005) == "0.0025-0.01"
    assert area_bin(0.02) == "0.01-0.04"
    assert area_bin(0.10) == "0.04-0.16"
    assert area_bin(0.20) == ">=0.16"

def test_parse_frame_idx():
    assert parse_frame_idx("frame_000123.txt") == 123
    assert parse_frame_idx("bad.txt") is None


def test_read_yolo_label_happy_path(tmp_path):
    path = tmp_path / "frame_000001.txt"
    path.write_text(
        "0 0.5 0.5 0.10 0.20\n"
        "1 0.3 0.3 0.30 0.30\n",
        encoding="utf-8",
    )
    n_boxes, class_counts, area_counts, ar_counts = read_yolo_label(path)

    assert n_boxes == 2
    assert class_counts == Counter({0: 1, 1: 1})
    assert sum(area_counts.values()) == 2
    assert sum(ar_counts.values()) == 2


def test_read_yolo_label_empty_file(tmp_path):
    path = tmp_path / "frame_000001.txt"
    path.write_text("", encoding="utf-8")

    n_boxes, class_counts, area_counts, ar_counts = read_yolo_label(path)
    assert n_boxes == 0
    assert class_counts == Counter()
    assert area_counts == Counter()
    assert ar_counts == Counter()


def test_read_yolo_label_bad_lines(tmp_path):
    path = tmp_path / "frame_000001.txt"
    path.write_text("bad line\n0 0.5 0.5 nope 0.2\n", encoding="utf-8")

    n_boxes, class_counts, area_counts, ar_counts = read_yolo_label(path)
    assert n_boxes == 1
    assert class_counts == Counter({0: 1})
    assert sum(area_counts.values()) == 1
    assert sum(ar_counts.values()) == 1
