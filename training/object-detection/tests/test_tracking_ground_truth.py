from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from object_detection.tracking_eval.ground_truth import (
    build_tracking_ground_truth,
    interpolate_track_sequence,
)


def write_eval_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["split", "video_stem", "site", "local_video_path"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_metadata_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "video_stem",
        "fps",
        "nb_frames",
        "duration",
        "width",
        "height",
        "org",
        "site",
        "device",
        "s3_key",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({name: row.get(name, "") for name in fieldnames})


def write_site_manifest(path: Path, raw_root: Path, json_paths: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "site": path.stem,
        "raw_root": str(raw_root),
        "files": [
            {"path": str(p.relative_to(raw_root))}
            for p in json_paths
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_item(
    *,
    stem: str,
    updated_at: str = "2026-01-01T00:00:00Z",
    result_id: str | None = "track-a",
    label: str = "Sockeye",
    seq: list[dict] | None = None,
) -> dict:
    if seq is None:
        seq = [
            {
                "frame": 0,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "rotation": 0,
                "enabled": True,
            },
            {
                "frame": 2,
                "x": 20,
                "y": 30,
                "width": 30,
                "height": 40,
                "rotation": 0,
                "enabled": True,
            },
        ]

    result = {
        "type": "videorectangle",
        "from_name": "box",
        "to_name": "video",
        "value": {
            "labels": [label],
            "sequence": seq,
        },
    }
    if result_id is not None:
        result["id"] = result_id

    return {
        "id": 123,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_organization_reference_string": "HIRMD",
            "metadata_file_camera_reference_string": "jetson-0",
            "metadata_file_filename": f"{stem}.mp4",
            "metadata_video_width": 1000,
            "metadata_video_height": 500,
            "metadata_video_nb_frames": 100,
            "metadata_video_duration": 10.0,
            "video": f"s3://bucket/HIRMD/tankeeah/jetson-0/motion_vids/{stem}.mp4",
        },
        "annotations": [
            {
                "updated_at": updated_at,
                "result": [result],
            }
        ],
    }


def setup_one_video(tmp_path: Path, *, item: dict | None = None):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    eval_csv = tmp_path / "val_videos.csv"
    write_eval_csv(
        eval_csv,
        [
            {
                "split": "val",
                "video_stem": stem,
                "site": "tankeeah",
                "local_video_path": f"videos/val/{stem}.mp4",
            }
        ],
    )

    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("names: [Sockeye, Coho]\n", encoding="utf-8")

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    json_path = raw_root / "export.json"
    if item is None:
        item = make_item(stem=stem)
    json_path.write_text(json.dumps([item]), encoding="utf-8")

    site_index_dir = tmp_path / "site_index"
    write_site_manifest(
        site_index_dir / "tankeeah.json",
        raw_root,
        [json_path],
    )

    return stem, eval_csv, data_yaml, raw_root, site_index_dir


def test_interpolate_sequence_matches_yolo_semantics():
    frames = interpolate_track_sequence(
        [
            {"frame": 0, "x": 0, "y": 0, "width": 10, "height": 20, "enabled": True},
            {"frame": 2, "x": 20, "y": 10, "width": 30, "height": 40, "enabled": False},
            {"frame": 4, "x": 40, "y": 20, "width": 50, "height": 60, "enabled": True},
        ]
    )

    assert [f.frame_idx for f in frames] == [0, 1, 2, 4]
    assert frames[1].x == pytest.approx(10)
    assert frames[1].y == pytest.approx(5)
    assert frames[1].width == pytest.approx(20)
    assert frames[1].height == pytest.approx(30)
    assert frames[1].is_keyframe is False
    assert frames[2].is_keyframe is True
    assert frames[2].keyframe_enabled is False
    # No frame 3 because disabled frame 2 does not interpolate forward.


def test_build_tracking_gt_writes_ids_pixels_and_mot_frames(tmp_path: Path):
    stem, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path)
    out_gt = tmp_path / "val_gt.csv"
    out_seq = tmp_path / "val_sequences.csv"

    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
        coord_mode="percent",
    )

    assert stats.videos_selected == 1
    assert stats.videos_with_tracks == 1
    assert stats.tracks_written == 1
    assert stats.gt_rows_written == 3

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert [int(r["frame_idx"]) for r in rows] == [0, 1, 2]
    assert [int(r["mot_frame"]) for r in rows] == [1, 2, 3]
    assert {r["track_id"] for r in rows} == {"1"}
    assert {r["track_uid"] for r in rows} == {"track-a"}
    assert {r["track_uid_source"] for r in rows} == {"label_studio"}
    assert float(rows[0]["x_px"]) == pytest.approx(100.0)
    assert float(rows[0]["y_px"]) == pytest.approx(100.0)
    assert float(rows[0]["width_px"]) == pytest.approx(300.0)
    assert float(rows[0]["height_px"]) == pytest.approx(200.0)
    assert rows[0]["is_keyframe"] == "true"
    assert rows[1]["is_keyframe"] == "false"

    seq_rows = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))
    assert seq_rows[0]["video_stem"] == stem
    assert seq_rows[0]["status"] == "ok"
    assert seq_rows[0]["n_tracks"] == "1"
    assert seq_rows[0]["n_gt_rows"] == "3"
    assert seq_rows[0]["width"] == "1000"
    assert seq_rows[0]["height"] == "500"


def test_latest_annotation_across_duplicate_exports_wins(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    eval_csv = tmp_path / "val_videos.csv"
    write_eval_csv(
        eval_csv,
        [{"split": "val", "video_stem": stem, "site": "tankeeah", "local_video_path": "x.mp4"}],
    )
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("names: [Sockeye, Coho]\n", encoding="utf-8")

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    old_path = raw_root / "old.json"
    new_path = raw_root / "new.json"
    old_path.write_text(
        json.dumps([make_item(stem=stem, updated_at="2025-01-01T00:00:00Z", label="Sockeye")]),
        encoding="utf-8",
    )
    new_path.write_text(
        json.dumps([make_item(stem=stem, updated_at="2026-01-01T00:00:00Z", label="Coho")]),
        encoding="utf-8",
    )
    site_index_dir = tmp_path / "site_index"
    write_site_manifest(site_index_dir / "tankeeah.json", raw_root, [old_path, new_path])

    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"
    build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
    )

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert {r["class_name"] for r in rows} == {"Coho"}
    assert {r["class_id"] for r in rows} == {"1"}
    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["source_json"].endswith("new.json")


def test_missing_label_studio_region_id_gets_synthetic_uid(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    item = make_item(stem=stem, result_id=None)
    _, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path, item=item)

    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"
    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
    )

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert rows[0]["track_uid"] == "synthetic_result_000000"
    assert rows[0]["track_uid_source"] == "synthetic_result_index"
    assert stats.synthetic_track_uids == 1


def test_condition_negative_without_ls_task_is_valid_zero_gt(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    eval_csv = tmp_path / "val_videos.csv"
    write_eval_csv(
        eval_csv,
        [{"split": "val", "video_stem": stem, "site": "tankeeah", "local_video_path": "x.mp4"}],
    )
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("names: [Sockeye]\n", encoding="utf-8")
    site_index_dir = tmp_path / "site_index"
    site_index_dir.mkdir()

    negatives = tmp_path / "negative_metadata.csv"
    write_metadata_csv(
        negatives,
        [{"video_stem": stem, "fps": "10", "nb_frames": "100", "width": "1280", "height": "720"}],
    )

    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"
    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
        negative_metadata_csv_paths=[negatives],
    )

    assert stats.videos_condition_negative == 1
    assert stats.videos_zero_gt == 1
    assert list(csv.DictReader(out_gt.open("r", encoding="utf-8"))) == []
    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["status"] == "condition_negative"
    assert seq["n_tracks"] == "0"


def test_missing_nonnegative_annotation_writes_diagnostics_then_raises(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    eval_csv = tmp_path / "val_videos.csv"
    write_eval_csv(
        eval_csv,
        [{"split": "val", "video_stem": stem, "site": "tankeeah", "local_video_path": "x.mp4"}],
    )
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("names: [Sockeye]\n", encoding="utf-8")
    site_index_dir = tmp_path / "site_index"
    site_index_dir.mkdir()
    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"

    with pytest.raises(RuntimeError, match="annotation not found"):
        build_tracking_ground_truth(
            eval_csv=eval_csv,
            site_index_dir=site_index_dir,
            data_yaml=data_yaml,
            out_gt_csv=out_gt,
            out_sequences_csv=out_seq,
        )

    assert out_gt.exists()
    assert out_seq.exists()
    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["status"] == "annotation_not_found"


def test_unknown_class_track_is_reported_but_not_written(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    item = make_item(stem=stem, label="MysteryFish")
    _, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path, item=item)

    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"
    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
    )

    assert stats.unknown_class_tracks == 1
    assert stats.videos_zero_gt == 1
    assert list(csv.DictReader(out_gt.open("r", encoding="utf-8"))) == []
    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["status"] == "no_tracks"
    assert seq["unknown_class_tracks"] == "1"


def test_degenerate_gt_rows_are_dropped_but_valid_track_is_kept(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    item = make_item(
        stem=stem,
        seq=[
            {"frame": 0, "x": 10, "y": 20, "width": 30, "height": 40, "rotation": 0, "enabled": True},
            {"frame": 1, "x": 11, "y": 21, "width": 0, "height": 40, "rotation": 0, "enabled": True},
            {"frame": 2, "x": 12, "y": 22, "width": 30, "height": 40, "rotation": 0, "enabled": True},
        ],
    )
    _, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path, item=item)
    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"

    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
        coord_mode="percent",
    )

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert [int(r["frame_idx"]) for r in rows] == [0, 2]
    assert {r["track_id"] for r in rows} == {"1"}
    assert all(float(r["width_px"]) > 0 for r in rows)
    assert all(float(r["height_px"]) > 0 for r in rows)

    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["status"] == "ok"
    assert seq["n_tracks"] == "1"
    assert seq["n_gt_rows"] == "2"
    assert seq["n_keyframes"] == "2"
    assert seq["degenerate_rows_dropped"] == "1"
    assert seq["degenerate_tracks_dropped"] == "0"
    assert stats.degenerate_rows_dropped == 1
    assert stats.degenerate_tracks_dropped == 0


def test_degenerate_only_track_is_removed_from_sequence_counts(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    item = make_item(
        stem=stem,
        seq=[
            {"frame": 5, "x": 10, "y": 20, "width": 0, "height": 4, "rotation": 0, "enabled": True},
        ],
    )
    _, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path, item=item)
    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"

    stats = build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
        coord_mode="percent",
    )

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert rows == []

    seq = list(csv.DictReader(out_seq.open("r", encoding="utf-8")))[0]
    assert seq["status"] == "no_tracks"
    assert seq["n_tracks"] == "0"
    assert seq["n_gt_rows"] == "0"
    assert seq["degenerate_rows_dropped"] == "1"
    assert seq["degenerate_tracks_dropped"] == "1"
    assert stats.videos_with_tracks == 0
    assert stats.videos_zero_gt == 1
    assert stats.tracks_written == 0
    assert stats.degenerate_rows_dropped == 1
    assert stats.degenerate_tracks_dropped == 1


def test_track_ids_are_contiguous_after_dropping_degenerate_only_track(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    first = make_item(
        stem=stem,
        result_id="bad-track",
        seq=[{"frame": 0, "x": 10, "y": 10, "width": 0, "height": 10, "rotation": 0, "enabled": True}],
    )
    good_result = {
        "id": "good-track",
        "type": "videorectangle",
        "from_name": "box",
        "to_name": "video",
        "value": {
            "labels": ["Sockeye"],
            "sequence": [
                {"frame": 2, "x": 10, "y": 20, "width": 30, "height": 40, "rotation": 0, "enabled": True},
            ],
        },
    }
    first["annotations"][0]["result"].append(good_result)

    _, eval_csv, data_yaml, _, site_index_dir = setup_one_video(tmp_path, item=first)
    out_gt = tmp_path / "gt.csv"
    out_seq = tmp_path / "seq.csv"
    build_tracking_ground_truth(
        eval_csv=eval_csv,
        site_index_dir=site_index_dir,
        data_yaml=data_yaml,
        out_gt_csv=out_gt,
        out_sequences_csv=out_seq,
        coord_mode="percent",
    )

    rows = list(csv.DictReader(out_gt.open("r", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["track_uid"] == "good-track"
    assert rows[0]["track_id"] == "1"
