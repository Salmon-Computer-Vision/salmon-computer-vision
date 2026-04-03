from pathlib import Path

import pytest

from object_detection.frames.parsing import (
    label_relpath_to_image_relpath,
    parse_frame_idx,
    parse_manifest_relpath,
    split_label_relpath_to_packed_paths,
    video_stem_to_s3_key,
)


def test_split_label_relpath_to_packed_paths_default_ext():
    image_rel, label_rel = split_label_relpath_to_packed_paths(
        split="train",
        relpath="HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt",
    )
    assert image_rel == Path("train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.jpg")
    assert label_rel == Path("train/HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt")


def test_split_label_relpath_to_packed_paths_png():
    image_rel, label_rel = split_label_relpath_to_packed_paths(
        split="val",
        relpath="HIRMD-tankeeah-jetson-1_20250714_012827_M/frame_000999.txt",
        image_ext=".png",
    )
    assert image_rel == Path("val/HIRMD-tankeeah-jetson-1_20250714_012827_M/frame_000999.png")
    assert label_rel == Path("val/HIRMD-tankeeah-jetson-1_20250714_012827_M/frame_000999.txt")


def test_parse_frame_idx_valid():
    assert parse_frame_idx("frame_000123.txt") == 123


def test_parse_frame_idx_invalid():
    assert parse_frame_idx("frame_abc.txt") is None
    assert parse_frame_idx("not_a_frame.txt") is None


def test_parse_manifest_relpath_valid():
    video_stem, frame_idx = parse_manifest_relpath(
        "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt"
    )
    assert video_stem == "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    assert frame_idx == 123


def test_parse_manifest_relpath_invalid():
    with pytest.raises(ValueError, match="Invalid manifest relpath"):
        parse_manifest_relpath("frame_000123.txt")

    with pytest.raises(ValueError, match="Invalid frame filename"):
        parse_manifest_relpath("HIRMD-tankeeah-jetson-0_20250714_012827_M/not_a_frame.txt")


def test_label_relpath_to_image_relpath():
    got = label_relpath_to_image_relpath(
        "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.txt",
        image_ext=".png",
    )
    assert got == Path("HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000123.png")


def test_video_stem_to_s3_key():
    got = video_stem_to_s3_key("HIRMD-tankeeah-jetson-0_20250714_012827_M")
    assert got == "HIRMD/tankeeah/jetson-0/motion_vids/HIRMD-tankeeah-jetson-0_20250714_012827_M.mp4"
