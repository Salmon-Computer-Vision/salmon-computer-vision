from __future__ import annotations

import csv
from pathlib import Path

import pytest

from importlib.util import module_from_spec, spec_from_file_location

script = Path(__file__).resolve().parents[1] / "scripts" / "build_verified_annotation_coverage.py"
spec = spec_from_file_location("build_verified_annotation_coverage", script)
assert spec and spec.loader
mod = module_from_spec(spec)
spec.loader.exec_module(mod)
build_coverage = mod.build_coverage

FIELDS = ["split", "video_stem", "status", "source_json", "n_gt_rows",
          "degenerate_tracks_dropped", "out_of_range_tracks_dropped", "fully_outside_tracks_dropped"]


def write_input(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({"split": "val", "source_json": "task.json", "n_gt_rows": "0",
                        "degenerate_tracks_dropped": "0", "out_of_range_tracks_dropped": "0",
                        "fully_outside_tracks_dropped": "0", **row})


def test_verified_labelstudio_task_and_empty_gt(tmp_path):
    inp, out = tmp_path / "sequences.csv", tmp_path / "coverage.csv"
    write_input(inp, [
        {"video_stem": "a", "status": "ok", "n_gt_rows": "5"},
        {"video_stem": "b", "status": "no_tracks"},
        {"video_stem": "c", "status": "condition_negative", "source_json": ""},
        {"video_stem": "d", "status": "annotation_not_found", "source_json": ""},
    ])
    counts = build_coverage(inp, out, split="val")
    with out.open(newline="", encoding="utf-8") as f:
        data = {r["video_stem"]: r for r in csv.DictReader(f)}
    assert [data[x]["fully_annotated"] for x in ("a", "b", "c", "d")] == ["true", "true", "false", "false"]
    assert counts == {"total": 4, "verified_with_gt": 1, "verified_empty_gt": 1,
                      "unverified": 2, "flagged_sanitized_empty": 0}


@pytest.mark.parametrize("column", ["degenerate_tracks_dropped", "out_of_range_tracks_dropped", "fully_outside_tracks_dropped"])
def test_sanitized_empty_requires_manual_review(tmp_path, column):
    inp, out = tmp_path / "sequences.csv", tmp_path / "coverage.csv"
    write_input(inp, [{"video_stem": "lost", "status": "no_tracks", column: "1"}])
    counts = build_coverage(inp, out, split="val")
    with out.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["fully_annotated"] == "false"
    assert row["review_basis"] == "empty_gt_after_dropped_tracks_requires_review"
    assert counts["flagged_sanitized_empty"] == 1


def test_missing_source_not_reviewed(tmp_path):
    inp, out = tmp_path / "sequences.csv", tmp_path / "coverage.csv"
    write_input(inp, [{"video_stem": "a", "status": "no_tracks", "source_json": ""}])
    assert build_coverage(inp, out, split="val")["verified_empty_gt"] == 0


def test_reject_duplicate_and_bad_metadata(tmp_path):
    inp, out = tmp_path / "sequences.csv", tmp_path / "coverage.csv"
    write_input(inp, [{"video_stem": "a", "status": "no_tracks"}, {"video_stem": "a", "status": "ok", "n_gt_rows": "1"}])
    with pytest.raises(ValueError, match="Duplicate"):
        build_coverage(inp, out, split="val")
    write_input(inp, [{"video_stem": "a", "status": "no_tracks", "n_gt_rows": "1"}])
    with pytest.raises(ValueError, match="no_tracks but"):
        build_coverage(inp, out, split="val")
    write_input(inp, [{"video_stem": "a", "status": "no_tracks", "split": "test"}])
    with pytest.raises(ValueError, match="Split mismatch"):
        build_coverage(inp, out, split="val")
