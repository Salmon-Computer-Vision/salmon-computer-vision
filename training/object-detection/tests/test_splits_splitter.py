import json
from collections import Counter
from pathlib import Path

import pytest

from object_detection.splits.splitter import (
    SplitState,
    build_groups,
    compute_global_targets,
    iter_label_files,
    l1_dist,
    normalize_counter,
    rarity_score,
    split_groups_greedy,
    summarize_split,
    write_manifest,
)


def test_iter_label_files(tmp_path: Path, make_label_file):
    make_label_file(tmp_path, "HIRMD-tankeeah-jetson-0_20250714_012827_M", 10, "0 0.5 0.5 0.1 0.2\n")
    make_label_file(tmp_path, "HIRMD-tankeeah-jetson-0_20250714_012827_M", 11, "0 0.5 0.5 0.1 0.2\n")
    files = sorted(iter_label_files(tmp_path))
    assert len(files) == 2
    assert files[0].name == "frame_000010.txt"


def test_build_groups_filters_sites(tmp_path: Path, make_label_file):
    make_label_file(
        tmp_path,
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
        10,
        "0 0.5 0.5 0.1 0.2\n",
    )
    make_label_file(
        tmp_path,
        "HIRMD-bear-jetsonnx-0_20250912_011859_M",
        20,
        "1 0.5 0.5 0.2 0.2\n",
    )

    groups = build_groups(tmp_path, sites_keep={"tankeeah"}, seed=42)

    assert len(groups) == 1
    gid = next(iter(groups))
    assert gid.startswith("tankeeah|")


def test_build_groups_aggregates_frames(tmp_path: Path, make_label_file):
    video = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    make_label_file(tmp_path, video, 10, "0 0.5 0.5 0.1 0.2\n")
    make_label_file(tmp_path, video, 11, "0 0.5 0.5 0.1 0.2\n1 0.5 0.5 0.2 0.2\n")

    groups = build_groups(tmp_path, sites_keep={"tankeeah"}, seed=42)
    g = next(iter(groups.values()))

    assert g.n_frames == 2
    assert g.n_boxes == 3
    assert g.class_counts == Counter({0: 2, 1: 1})
    assert len(g.frame_paths) == 2


def test_normalize_counter():
    got = normalize_counter(Counter({"a": 2, "b": 1}))
    assert got["a"] == pytest.approx(2 / 3)
    assert got["b"] == pytest.approx(1 / 3)


def test_l1_dist():
    p = {"a": 0.5, "b": 0.5}
    q = {"a": 1.0, "b": 0.0}
    assert l1_dist(p, q, ["a", "b"]) == pytest.approx(1.0)


def test_compute_global_targets(tmp_path: Path, make_label_file):
    video1 = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    video2 = "HIRMD-bear-jetsonnx-0_20250912_011859_M"
    make_label_file(tmp_path, video1, 10, "0 0.5 0.5 0.1 0.2\n")
    make_label_file(tmp_path, video2, 20, "1 0.5 0.5 0.2 0.2\n")

    groups = build_groups(tmp_path, sites_keep={"tankeeah", "bear"}, seed=42)
    targets = compute_global_targets(list(groups.values()))

    assert targets["total_frames"] == 2
    assert targets["class_keys"] == [0, 1]
    assert pytest.approx(sum(targets["class_dist"].values())) == 1.0


def test_rarity_score_positive(tmp_path: Path, make_label_file):
    video = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    make_label_file(tmp_path, video, 10, "0 0.5 0.5 0.1 0.2\n")
    groups = build_groups(tmp_path, sites_keep={"tankeeah"}, seed=42)
    g = next(iter(groups.values()))
    score = rarity_score(g, {0: 1.0})
    assert score > 0


def test_split_groups_greedy_assigns_all_groups(tmp_path: Path, make_label_file):
    videos = [
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
        "HIRMD-tankeeah-jetson-0_20250715_012827_M",
        "HIRMD-kitwanga-jetson-0_20250714_012827_M",
        "SFC-bear-jetsonnx-0_20250912_011859_M",
    ]
    for i, video in enumerate(videos):
        make_label_file(tmp_path, video, 10, f"{i % 2} 0.5 0.5 0.1 0.2\n")

    groups = build_groups(tmp_path, sites_keep={"tankeeah", "kitwanga", "bear"}, seed=42)
    train, val, test, report = split_groups_greedy(
        groups=groups,
        seed=42,
        train_frac=0.8,
        val_frac=0.1,
        test_frac=0.1,
        weights={"class": 4.0, "tod": 1.0, "density": 1.0, "area": 1.0, "size": 2.0},
    )

    assigned = set(train.group_ids) | set(val.group_ids) | set(test.group_ids)
    assert assigned == set(groups.keys())
    assert report["total_frames"] == 4
    assert train.n_frames + val.n_frames + test.n_frames == 4


def test_summarize_split(tmp_path: Path, make_label_file):
    video = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    make_label_file(tmp_path, video, 10, "0 0.5 0.5 0.1 0.2\n")
    groups = build_groups(tmp_path, sites_keep={"tankeeah"}, seed=42)
    g = next(iter(groups.values()))

    split = SplitState("train", 0.8)
    split.add_group(g)

    summary = summarize_split(split)
    assert summary["n_frames"] == 1
    assert summary["n_boxes"] == 1
    assert summary["n_groups"] == 1


def test_write_manifest(tmp_path: Path):
    out = tmp_path / "manifest.txt"
    write_manifest(out, ["b/file2.txt", "a/file1.txt"])
    assert out.read_text(encoding="utf-8") == "a/file1.txt\nb/file2.txt\n"
