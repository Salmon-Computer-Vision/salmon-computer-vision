from __future__ import annotations

import configparser
import csv
import json
from pathlib import Path

import pytest

from object_detection.tracking_eval.mot_format import (
    MotGtRow,
    format_motchallenge_gt_row,
    materialize_mot_ground_truth,
    validate_motchallenge_gt_lines,
)


SEQ_FIELDS = [
    "split", "video_stem", "site", "status", "source_json",
    "annotation_updated_at", "width", "height", "fps", "nb_frames",
    "n_tracks", "n_gt_rows", "n_keyframes", "unknown_class_tracks",
    "synthetic_track_uids", "rotated_rows", "local_video_path",
]

GT_FIELDS = [
    "split", "video_stem", "site", "frame_idx", "mot_frame", "track_id",
    "track_uid", "track_uid_source", "class_id", "class_name",
    "x_px", "y_px", "width_px", "height_px", "xc_norm", "yc_norm",
    "width_norm", "height_norm", "rotation_deg", "is_keyframe",
    "keyframe_enabled", "source_json",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def seq_row(stem: str, *, split="val", n_tracks=1, n_gt_rows=2, rotated_rows=0, **overrides):
    row = {
        "split": split,
        "video_stem": stem,
        "site": "tankeeah",
        "status": "ok" if n_tracks else "condition_negative",
        "source_json": "source.json",
        "annotation_updated_at": "2026-01-01T00:00:00Z",
        "width": "1280",
        "height": "720",
        "fps": "10",
        "nb_frames": "100",
        "n_tracks": str(n_tracks),
        "n_gt_rows": str(n_gt_rows),
        "n_keyframes": "2" if n_gt_rows else "0",
        "unknown_class_tracks": "0",
        "synthetic_track_uids": "0",
        "rotated_rows": str(rotated_rows),
        "local_video_path": f"videos/{split}/{stem}.mp4",
    }
    row.update({k: str(v) for k, v in overrides.items()})
    return row


def gt_row(stem: str, mot_frame: int, track_id: int, *, split="val", rotation=0, **overrides):
    row = {
        "split": split,
        "video_stem": stem,
        "site": "tankeeah",
        "frame_idx": str(mot_frame - 1),
        "mot_frame": str(mot_frame),
        "track_id": str(track_id),
        "track_uid": f"track-{track_id}",
        "track_uid_source": "label_studio",
        "class_id": "0",
        "class_name": "Sockeye",
        "x_px": "10",
        "y_px": "20",
        "width_px": "30",
        "height_px": "40",
        "xc_norm": "0.1",
        "yc_norm": "0.2",
        "width_norm": "0.02",
        "height_norm": "0.05",
        "rotation_deg": str(rotation),
        "is_keyframe": "true",
        "keyframe_enabled": "true",
        "source_json": "source.json",
    }
    row.update({k: str(v) for k, v in overrides.items()})
    return row


def materialize(tmp_path: Path, sequences: list[dict], gt: list[dict], **kwargs):
    seq_csv = tmp_path / "sequences.csv"
    gt_csv = tmp_path / "gt.csv"
    out_root = tmp_path / "mot_gt"
    summary = tmp_path / "summary.json"
    write_csv(seq_csv, SEQ_FIELDS, sequences)
    write_csv(gt_csv, GT_FIELDS, gt)
    stats = materialize_mot_ground_truth(
        gt_csv=gt_csv,
        sequences_csv=seq_csv,
        out_root=out_root,
        benchmark="SalmonVision",
        split="val",
        summary_json=summary,
        **kwargs,
    )
    return stats, out_root, summary


def test_format_mot_gt_row_is_nine_column_motchallenge_gt():
    row = MotGtRow("video", 1, 2, 11.0, 21.0, 30.0, 40.0, 0.0)
    line = format_motchallenge_gt_row(row)
    parts = line.split(",")
    assert len(parts) == 9
    assert parts == [
        "1", "2", "11.000000", "21.000000", "30.000000", "40.000000",
        "1", "1", "1.000000",
    ]


def test_materializes_trackeval_directory_seqmap_seqinfo_and_gt(tmp_path: Path):
    a = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    b = "HIRMD-tankeeah-jetson-0_20250714_012900_M"
    stats, root, summary = materialize(
        tmp_path,
        [seq_row(a), seq_row(b, n_tracks=0, n_gt_rows=0)],
        [gt_row(a, 1, 1), gt_row(a, 2, 1, x_px=12.5, y_px=22.5)],
    )

    split_root = root / "SalmonVision-val"
    assert (split_root / a / "gt" / "gt.txt").is_file()
    assert (split_root / a / "seqinfo.ini").is_file()
    assert (split_root / b / "gt" / "gt.txt").is_file()
    assert (split_root / b / "seqinfo.ini").is_file()

    # Canonical pixels are zero-based; MOTChallenge bbox origins are materialized 1-based.
    lines = (split_root / a / "gt" / "gt.txt").read_text().splitlines()
    assert lines[0] == "1,1,11.000000,21.000000,30.000000,40.000000,1,1,1.000000"
    assert lines[1] == "2,1,13.500000,23.500000,30.000000,40.000000,1,1,1.000000"
    assert (split_root / b / "gt" / "gt.txt").read_text() == ""

    seqmap = (root / "seqmaps" / "SalmonVision-val.txt").read_text().splitlines()
    assert seqmap == ["name", a, b]

    cfg = configparser.ConfigParser()
    cfg.read(split_root / a / "seqinfo.ini")
    sec = cfg["Sequence"]
    assert sec["name"] == a
    assert sec["imDir"] == "img1"
    assert sec["frameRate"] == "10"
    assert sec["seqLength"] == "100"
    assert sec["imWidth"] == "1280"
    assert sec["imHeight"] == "720"
    assert sec["imExt"] == ".jpg"

    assert stats.sequences_written == 2
    assert stats.zero_gt_sequences == 1
    assert stats.gt_rows_written == 2
    assert stats.tracks_written == 1
    assert json.loads(summary.read_text())["gt_rows_written"] == 2


def test_gt_rows_sorted_by_frame_then_id(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    _, root, _ = materialize(
        tmp_path,
        [seq_row(stem, n_tracks=2, n_gt_rows=3)],
        [gt_row(stem, 2, 2), gt_row(stem, 1, 2), gt_row(stem, 1, 1)],
    )
    rows = (root / "SalmonVision-val" / stem / "gt" / "gt.txt").read_text().splitlines()
    assert [(int(x.split(",")[0]), int(x.split(",")[1])) for x in rows] == [(1, 1), (1, 2), (2, 2)]


def test_rebuild_removes_stale_sequence_directories(tmp_path: Path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    stats, root, _ = materialize(tmp_path, [seq_row(stem)], [gt_row(stem, 1, 1), gt_row(stem, 2, 1)])
    stale = root / "SalmonVision-val" / "STALE" / "gt"
    stale.mkdir(parents=True)
    (stale / "gt.txt").write_text("junk")
    materialize(tmp_path, [seq_row(stem)], [gt_row(stem, 1, 1), gt_row(stem, 2, 1)])
    assert not (root / "SalmonVision-val" / "STALE").exists()


def test_rejects_duplicate_frame_track_pair(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="Duplicate"):
        materialize(tmp_path, [seq_row(stem)], [gt_row(stem, 1, 1), gt_row(stem, 1, 1)])


def test_rejects_gt_frame_beyond_sequence_length(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="exceeds seqLength"):
        materialize(tmp_path, [seq_row(stem, nb_frames=1, n_gt_rows=1)], [gt_row(stem, 2, 1)])


@pytest.mark.parametrize("field,value,match", [
    ("mot_frame", 0, "frame must be >= 1"),
    ("track_id", 0, "track_id must be >= 1"),
    ("width_px", 0, "positive width/height"),
    ("height_px", -1, "positive width/height"),
    ("x_px", "nan", "Non-finite"),
])
def test_rejects_invalid_gt_values(tmp_path: Path, field, value, match):
    stem = "v_20250101_000000_M"
    row = gt_row(stem, 1, 1)
    row[field] = str(value)
    with pytest.raises(ValueError, match=match):
        materialize(tmp_path, [seq_row(stem, n_gt_rows=1)], [row])


@pytest.mark.parametrize("field,value,match", [
    ("width", 0, "Non-positive dimensions"),
    ("height", 0, "Non-positive dimensions"),
    ("fps", 0, "Non-positive fps"),
    ("nb_frames", 0, "Non-positive nb_frames"),
])
def test_rejects_invalid_sequence_metadata(tmp_path: Path, field, value, match):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match=match):
        materialize(tmp_path, [seq_row(stem, **{field: value})], [gt_row(stem, 1, 1), gt_row(stem, 2, 1)])


def test_rejects_sequence_split_mismatch(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="expected 'val'"):
        materialize(tmp_path, [seq_row(stem, split="test")], [])


def test_rejects_gt_split_mismatch(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="expected 'val'"):
        materialize(tmp_path, [seq_row(stem, n_gt_rows=1)], [gt_row(stem, 1, 1, split="test")])


def test_rejects_gt_for_sequence_missing_from_sequence_table(tmp_path: Path):
    a = "a_20250101_000000_M"
    b = "b_20250101_000000_M"
    with pytest.raises(ValueError, match="absent from sequences CSV"):
        materialize(tmp_path, [seq_row(a, n_tracks=0, n_gt_rows=0)], [gt_row(b, 1, 1)])


def test_rejects_n_gt_rows_mismatch(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="n_gt_rows mismatch"):
        materialize(tmp_path, [seq_row(stem, n_gt_rows=2)], [gt_row(stem, 1, 1)])


def test_rejects_n_tracks_mismatch(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="n_tracks mismatch"):
        materialize(tmp_path, [seq_row(stem, n_tracks=2, n_gt_rows=1)], [gt_row(stem, 1, 1)])


def test_rotated_label_studio_box_is_materialized_as_axis_aligned_aabb(tmp_path: Path):
    stem = "v_20250101_000000_M"
    sequences = [seq_row(stem, n_gt_rows=1, rotated_rows=1, width=100, height=100)]
    # LS stores rotation around the exported top-left anchor. A 10x20 box at
    # (10,20) rotated +90 degrees has corners (10,20), (10,30), (-10,30),
    # (-10,20). After clipping to the image the visible AABB is x=[0,10],
    # y=[20,30], then MOT origin becomes 1-based.
    gt = [gt_row(
        stem, 1, 1, rotation=90.0,
        x_px=10, y_px=20, width_px=10, height_px=20,
    )]
    stats, root, _ = materialize(tmp_path, sequences, gt)
    line = (root / "SalmonVision-val" / stem / "gt" / "gt.txt").read_text().strip()
    parts = line.split(",")
    assert parts[:2] == ["1", "1"]
    assert float(parts[2]) == pytest.approx(1.0)
    assert float(parts[3]) == pytest.approx(21.0)
    assert float(parts[4]) == pytest.approx(10.0)
    assert float(parts[5]) == pytest.approx(10.0)
    assert stats.rotated_rows == 1
    assert stats.clipped_rows == 1


def test_out_of_frame_axis_aligned_box_is_clipped_to_visible_image(tmp_path: Path):
    stem = "v_20250101_000000_M"
    sequences = [seq_row(stem, n_gt_rows=1, width=100, height=80)]
    gt = [gt_row(
        stem, 1, 1, x_px=-5, y_px=-2, width_px=20, height_px=10,
    )]
    stats, root, _ = materialize(tmp_path, sequences, gt)
    parts = (root / "SalmonVision-val" / stem / "gt" / "gt.txt").read_text().strip().split(",")
    assert float(parts[2]) == pytest.approx(1.0)
    assert float(parts[3]) == pytest.approx(1.0)
    assert float(parts[4]) == pytest.approx(15.0)
    assert float(parts[5]) == pytest.approx(8.0)
    assert stats.clipped_rows == 1


def test_rejects_fully_outside_box_instead_of_silently_dropping_it(tmp_path: Path):
    stem = "v_20250101_000000_M"
    sequences = [seq_row(stem, n_gt_rows=1, width=100, height=80)]
    gt = [gt_row(stem, 1, 1, x_px=-30, y_px=10, width_px=10, height_px=10)]
    with pytest.raises(ValueError, match="fully outside"):
        materialize(tmp_path, sequences, gt)


def test_rejects_rotated_row_count_mismatch(tmp_path: Path):
    stem = "v_20250101_000000_M"
    with pytest.raises(ValueError, match="rotated_rows mismatch"):
        materialize(
            tmp_path,
            [seq_row(stem, n_gt_rows=1, rotated_rows=0)],
            [gt_row(stem, 1, 1, rotation=1.0)],
        )


def test_validate_motchallenge_gt_lines_rejects_ten_column_tracker_style_row():
    # This specifically protects against confusing the MOT tracker/result 10-column
    # layout with TrackEval's MOT16/17-style GT layout, where col 7 is mark and
    # col 8 is class.
    with pytest.raises(ValueError, match="must contain 9 MOT GT columns"):
        validate_motchallenge_gt_lines(
            ["1,1,10,20,30,40,1,-1,-1,-1"],
            seq_length=100,
            sequence="seq",
        )


def test_seqmap_is_deterministic_alphabetical(tmp_path: Path):
    a = "A-site-jetson-0_20250101_000000_M"
    z = "Z-site-jetson-0_20250101_000000_M"
    _, root, _ = materialize(
        tmp_path,
        [seq_row(z, n_tracks=0, n_gt_rows=0), seq_row(a, n_tracks=0, n_gt_rows=0)],
        [],
    )
    assert (root / "seqmaps" / "SalmonVision-val.txt").read_text().splitlines() == ["name", a, z]


def test_cli_wrapper_smoke(tmp_path: Path, monkeypatch, capsys):
    from object_detection.tracking_eval.mot_format import main

    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    seq_csv = tmp_path / "seq.csv"
    gt_csv = tmp_path / "gt.csv"
    write_csv(seq_csv, SEQ_FIELDS, [seq_row(stem, n_gt_rows=1)])
    write_csv(gt_csv, GT_FIELDS, [gt_row(stem, 1, 1)])
    out = tmp_path / "mot"
    summary = tmp_path / "summary.json"

    main([
        "--gt-csv", str(gt_csv),
        "--sequences-csv", str(seq_csv),
        "--out-root", str(out),
        "--benchmark", "SalmonVision",
        "--split", "val",
        "--summary-json", str(summary),
    ])
    assert (out / "SalmonVision-val" / stem / "gt" / "gt.txt").exists()
    assert "MOT GT materialized" in capsys.readouterr().out


def test_rejects_annotation_not_found_sequence_status(tmp_path: Path):
    stem = "v_20250101_000000_M"
    bad = seq_row(stem, n_tracks=0, n_gt_rows=0)
    bad["status"] = "annotation_not_found"
    with pytest.raises(ValueError, match="non-evaluable GT status"):
        materialize(tmp_path, [bad], [])


def test_rejects_inconsistent_zero_gt_status_counts(tmp_path: Path):
    stem = "v_20250101_000000_M"
    bad = seq_row(stem, n_tracks=1, n_gt_rows=1)
    bad["status"] = "condition_negative"
    with pytest.raises(ValueError, match="Zero-GT sequence"):
        materialize(tmp_path, [bad], [gt_row(stem, 1, 1)])
