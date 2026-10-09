"""Regression tests for sampling empty frames inside reviewed LS videos.

pytest -q tests/test_annotated_negative_sampling.py
"""
import csv
import json
import tarfile
from pathlib import Path

import pytest

from object_detection.yolo_ls.converter import YoloConverterLSVideo
from object_detection.yolo_ls.cli import build_parser


def item(stem, site="stephenssmolt", n=30, rectangles=None):
    rectangles = rectangles or []
    return {
        "data": {
            "metadata_file_filename": stem + ".mp4",
            "metadata_file_site_reference_string": site,
            "metadata_video_nb_frames": n,
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
        },
        "annotations": [{
            "updated_at": "2026-10-01T00:00:00Z",
            "result": [{
                "type": "videorectangle",
                "value": {"labels": [label], "sequence": [
                    {"frame": f, "x": 1, "y": 2, "width": 5, "height": 6,
                     "enabled": True}
                    for f in frames]}
            } for label, frames in rectangles]
        }],
    }


def setup_converter(tmp_path, **kwargs):
    defaults = dict(
        class_map={"Sockeye": 0, "Coho": 1},
        output_dir=tmp_path / "fs",
        shard_dir=tmp_path / "shards",
        stats_dir=tmp_path / "stats",
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
        include_negatives=True,
        negative_ratio=0.25,
        negatives_per_video=10,
        annotated_negative_sites=["stephenssmolt"],
        annotated_negatives_per_video=12,
        negative_exclusion_frames=2,
    )
    defaults.update(kwargs)
    return YoloConverterLSVideo(**defaults)


def run(tmp_path, items, **kwargs):
    conv = setup_converter(tmp_path, **kwargs)
    data = tmp_path / "items.json"
    data.write_text(json.dumps(items), encoding="utf-8")
    stats = conv.convert_file(data)
    assert stats.errors == 0
    n, cap, available = conv.materialize_negatives()
    conv.export_stats()
    conv._sharder.close()
    with tarfile.open(next((tmp_path / "shards").glob("*.tar"))) as tf:
        contents = {m.name: tf.extractfile(m).read().decode("utf-8") for m in tf.getmembers()}
    return conv, stats, n, cap, available, contents


def test_annotated_video_samples_only_unoccupied_frames(tmp_path):
    stem = "GWA-stephenssmolt-jetsonnx-1_20261001_000000_M"
    conv, s, n, cap, available, data = run(tmp_path, [
        item(stem, n=36, rectangles=[("Sockeye", [3, 12])]),
    ])
    assert s.label_files_written == 4   # frames 3, 6, 9, 12 on stride 3
    assert n == 1  # <=25% of final: floor((.25/.75)*4)
    assert conv._negative_report["selected_from_annotated_videos"] == n
    assert conv._negative_report["selected_from_empty_videos"] == 0
    positive = {3, 6, 9, 12}
    forbidden = {f for x in range(3, 13) for f in range(x - 2, x + 3)}
    negative = {int(p.split("frame_")[1].split(".")[0]) for p, txt in data.items() if txt == ""}
    assert negative and negative.isdisjoint(forbidden)
    assert negative.isdisjoint(positive)
    assert len(data) == s.label_files_written + n


def test_empty_and_annotated_sources_both_contribute(tmp_path):
    positive = "GWA-stephenssmolt-jetsonnx-1_20261001_000001_M"
    empty = "GWA-stephenssmolt-jetsonnx-1_20261001_000002_M"
    conv, s, n, cap, available, data = run(tmp_path, [
        item(positive, n=100, rectangles=[("Sockeye", [12, 21, 30, 39, 48, 57, 66, 75, 84])]),
        item(empty, n=100),
    ])
    report = conv._negative_report
    assert n <= cap
    assert report["selected_from_empty_videos"] > 0
    assert report["selected_from_annotated_videos"] > 0
    assert report["selected_negative_files"] == n
    assert report["final_negative_fraction"] <= .25
    summary = json.loads((tmp_path/"stats"/"summary.json").read_text())
    assert summary["negative_sampling"]["selected_negative_files"] == n
    other = json.loads((tmp_path/"stats"/"negative_summary.json").read_text())
    assert other == report
    with (tmp_path/"stats"/"negative_video_counts.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert sum(int(r["selected_negative_frames"]) for r in rows) == n
    with (tmp_path/"stats"/"site_negative_counts.csv").open() as f:
        sites = list(csv.DictReader(f))
    assert len(sites) == 1
    assert int(sites[0]["negative_total"]) == n


def test_disabled_site_only_uses_empty_video(tmp_path):
    pos = "HIRMD-tankeeah-jetson-0_20261001_000001_M"
    neg = "HIRMD-tankeeah-jetson-0_20261001_000002_M"
    conv, s, n, cap, available, data = run(tmp_path, [
        item(pos, site="tankeeah", n=50, rectangles=[("Sockeye", [0, 12, 24, 36])]),
        item(neg, site="tankeeah", n=50),
    ])
    assert n > 0
    assert conv._negative_report["selected_from_annotated_videos"] == 0
    assert all(neg in path for path, txt in data.items() if not txt)


def test_unknown_class_is_not_turned_into_negative(tmp_path):
    pos = "GWA-stephenssmolt-jetsonnx-1_20261001_000003_M"
    conv, s, n, cap, avail, data = run(tmp_path, [
        item(pos, n=45, rectangles=[("Sockeye", [3, 6]), ("Unknown", [18, 21])]),
    ])
    assert n == 0
    assert conv._negative_report["selected_from_annotated_videos"] == 0
    assert any("frame_000003" in p for p in data)


def test_no_negatives_without_annotation_and_positive_files(tmp_path):
    stem = "GWA-stephenssmolt-jetsonnx-1_20261001_000004_M"
    conv, s, n, cap, avail, data = run(tmp_path, [item(stem, n=100)])
    assert n == 0
    assert cap == 0


def test_deterministic_across_runs_and_input_task_order(tmp_path):
    a = item("GWA-stephenssmolt-jetsonnx-1_20261001_000005_M", rectangles=[("Sockeye", [3, 6, 9])], n=60)
    b = item("GWA-stephenssmolt-jetsonnx-1_20261001_000006_M", n=60)
    out1 = run(tmp_path / "one", [a, b])
    out2 = run(tmp_path / "two", [b, a])
    assert out1[-1] == out2[-1]
    assert out1[2:5] == out2[2:5]


def test_positive_occupancy_can_be_unaligned_to_stride(tmp_path):
    stem = "GWA-stephenssmolt-jetsonnx-1_20261001_000007_M"
    conv, s, n, cap, avail, data = run(tmp_path, [
        item(stem, n=60, rectangles=[("Sockeye", [1, 13, 25])]),
    ])
    assert all(not (0 <= int(p.split("frame_")[1].split(".")[0]) <= 27)
               for p, txt in data.items() if txt == "")


def test_cli_parser_and_yaml_wiring():
    args = build_parser().parse_args(["--data-yaml", "x.yaml", "--out", "out",
        "--annotated-negative-sites", "stephenssmolt", "--annotated-negatives-per-video", "18",
        "--negative-exclusion-frames", "4"])
    assert args.annotated_negative_sites == "stephenssmolt"
    assert args.annotated_negatives_per_video == 18
    assert args.negative_exclusion_frames == 4
    import yaml
    root = Path(__file__).resolve().parents[1]
    dvc = yaml.safe_load((root / "dvc.yaml").read_text())
    params = yaml.safe_load((root / "params.yaml").read_text())
    stage = dvc["stages"]["build_model_input"]["do"]
    assert "--annotated-negative-sites" in stage["cmd"]
    assert "data.neg_annotated_sites" in stage["params"]
    assert params["data"]["neg_annotated_sites"] == "stephenssmolt"


def test_invalid_ratio_or_margin(tmp_path):
    with pytest.raises(ValueError, match="negative_ratio"):
        setup_converter(tmp_path, negative_ratio=1.2)


def test_cli_end_to_end_writes_shards_and_stats(tmp_path, monkeypatch, capsys):
    """Exercise the real CLI path, not just the converter methods."""
    stem = "GWA-stephenssmolt-jetsonnx-0_20261001_000008_M"
    data = tmp_path / "input.json"
    data.write_text(json.dumps([item(stem, n=81, rectangles=[("Sockeye", [3, 12, 21, 30, 39, 48])])]))
    config = tmp_path / "data.yaml"
    config.write_text("names:\n  0: Sockeye\n  1: Coho\n")
    import sys
    from object_detection.yolo_ls import cli
    monkeypatch.setattr(sys, "argv", ["converter", str(data),
        "--data-yaml", str(config), "--out", str(tmp_path / "fs"),
        "--out-shards", str(tmp_path / "shards"),
        "--include-negatives", "--negative-ratio", "0.3",
        "--annotated-negative-sites", "stephenssmolt",
        "--annotated-negatives-per-video", "12",
        "--negative-exclusion-frames", "0",
        "--frame-stride", "3", "--frame-offset-mode", "fixed", "--frame-offset", "0",
        "--stats-dir", str(tmp_path / "stats")])
    cli.main()
    output = capsys.readouterr().out
    assert "negative_from_annotated=" in output
    summary = json.loads((tmp_path / "stats" / "negative_summary.json").read_text())
    assert summary["selected_from_annotated_videos"] > 0
    assert summary["selected_from_empty_videos"] == 0
    with (tmp_path / "stats" / "site_totals.csv").open() as f:
        row = next(csv.DictReader(f))
    assert int(row["negative_from_annotated"]) == summary["selected_negative_files"]
    assert int(row["total_frames_including_negatives"]) == (
        int(row["total_frames_with_boxes"]) + int(row["negative_total"]))
