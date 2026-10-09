import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from object_detection.tracking_eval.eval_common import (
    select_sequences, predictions_by_video, write_csv,
)
from object_detection.tracking_eval.tracking_metrics import (
    format_tracker_mot_row, make_mot_workspace, trackeval_metrics,
    evaluate_tracking,
)


def fixtures(tmp, *, include_empty=True):
    seqs = [
        dict(split="val", video_stem="fish-a", site="river", nb_frames=3, n_gt_rows=2,
             n_tracks=1, rotated_rows=0, status="ok", width=100, height=50, fps=10),
        dict(split="val", video_stem="fish-b", site="river", nb_frames=3, n_gt_rows=0,
             n_tracks=0, rotated_rows=0, status="no_tracks", width=100, height=50, fps=10),
    ]
    if not include_empty:
        seqs = seqs[:1]
    statuses = [dict(split="val", video_stem=s["video_stem"], status="ok",
                     eligible_for_evaluation=True, frames_decoded=3,
                     predictions_written=2 if s["video_stem"] == "fish-a" else 0) for s in seqs]
    gt = [dict(split="val", video_stem="fish-a", frame_idx=i, mot_frame=i+1, track_id=1,
               class_id=0, x_px=10+50*i, y_px=10, width_px=15, height_px=10,
               rotation_deg=0) for i in (0, 1)]
    paths = {}
    for name, rows in [("sequences", seqs), ("status", statuses), ("gt", gt)]:
        path = tmp / f"{name}.csv"
        cols = list(rows[0])
        write_csv(path, rows, cols)
        paths[name] = path
    return paths, seqs, statuses, gt


def test_default_excludes_empty_gt(tmp_path):
    paths, _, _, _ = fixtures(tmp_path)
    selected, ledger = select_sequences(sequence_csv=paths["sequences"],
        inference_status_csv=paths["status"], split="val")
    assert list(selected) == ["fish-a"]
    assert ledger[1]["reason"] == "no_gt_coverage_unverified"


def test_verified_requires_review_csv(tmp_path):
    paths, _, _, _ = fixtures(tmp_path)
    with pytest.raises(ValueError, match="coverage-csv"):
        select_sequences(sequence_csv=paths["sequences"], inference_status_csv=paths["status"],
                         split="val", scope="verified")
    cov = tmp_path / "coverage.csv"
    write_csv(cov, [dict(video_stem="fish-a", fully_annotated=True),
                    dict(video_stem="fish-b", fully_annotated=True)],
              ["video_stem", "fully_annotated"])
    selected, _ = select_sequences(sequence_csv=paths["sequences"], inference_status_csv=paths["status"],
                                   split="val", scope="verified", coverage_csv=cov)
    assert set(selected) == {"fish-a", "fish-b"}


def test_frame_mismatch_excluded(tmp_path):
    paths, seqs, status, _ = fixtures(tmp_path, include_empty=False)
    status[0]["frames_decoded"] = 4
    write_csv(paths["status"], status, list(status[0]))
    selected, ledger = select_sequences(sequence_csv=paths["sequences"], inference_status_csv=paths["status"], split="val")
    assert not selected
    assert ledger[0]["reason"] == "decoded_frame_count_mismatch"


def test_prediction_mot_class_and_1_based_coordinate():
    row = dict(mot_frame=1, track_id=3, x_px=-2, y_px=-3, width_px=10, height_px=9, confidence=0.8)
    values = format_tracker_mot_row(row, width=100, height=50).split(",")
    assert len(values) == 10
    assert values[:2] == ["1", "3"]
    assert values[2:6] == ["1.000000", "1.000000", "8.000000", "6.000000"]
    assert values[7] == "1"  # TrackEval's eighth column is tracker class


def test_prediction_outside_fails():
    with pytest.raises(ValueError, match="fully outside"):
        format_tracker_mot_row(dict(mot_frame=1, track_id=1, x_px=200, y_px=5,
                                    width_px=10, height_px=8, confidence=.8), width=100, height=50)


def test_make_workspace_correct_split_and_empty_tracker_file(tmp_path):
    paths, seqs, statuses, gt = fixtures(tmp_path)
    selected = {s["video_stem"]: s for s in seqs}
    gt_root, tracks_root = make_mot_workspace(
        directory=tmp_path / "work", gt_csv=paths["gt"], sequence_csv=paths["sequences"],
        split="val", benchmark="SalmonVision", tracker="botsort",
        selected=selected, predictions={"fish-a": [dict(mot_frame=1, track_id=1,
          x_px=10, y_px=10, width_px=15, height_px=10, confidence=.8)]})
    assert (gt_root / "SalmonVision-val/fish-a/gt/gt.txt").exists()
    assert (gt_root / "SalmonVision-val/fish-b/gt/gt.txt").read_text() == ""
    assert (tracks_root / "SalmonVision-val/botsort/data/fish-b.txt").read_text() == ""
    assert (gt_root / "seqmaps/SalmonVision-val.txt").read_text().splitlines() == ["name", "fish-a", "fish-b"]


class FakeDataset:
    def __init__(self, config):
        self.config = config
    def get_name(self):
        return "MotChallenge2DBox"


class FakeEvaluator:
    def __init__(self, config):
        self.config = config
    def evaluate(self, datasets, metric_list):
        ds = datasets[0]
        assert ds.config["DO_PREPROC"] is False
        assert ds.config["CLASSES_TO_EVAL"] == ["pedestrian"]
        assert len(metric_list) == 3
        assert Path(ds.config["SEQMAP_FILE"]).exists()
        tracker = ds.config["TRACKERS_TO_EVAL"][0]
        names = Path(ds.config["SEQMAP_FILE"]).read_text().splitlines()[1:]
        def record():
            return dict(HOTA=dict(HOTA=[.8, .6], DetA=[.9, .7], AssA=[.5, .3]),
                CLEAR=dict(MOTA=.6, MOTP=.75, CLR_FP=1, CLR_FN=2, CLR_TP=3, IDSW=0),
                Identity=dict(IDF1=.8, IDP=.7, IDR=.9))
        results = {name: {"pedestrian": record()} for name in names}
        results["COMBINED_SEQ"] = {"pedestrian": record()}
        return {ds.get_name(): {tracker: results}}, {ds.get_name(): {tracker: "Success"}}


def fake_trackeval():
    return SimpleNamespace(datasets=SimpleNamespace(MotChallenge2DBox=FakeDataset),
                           Evaluator=FakeEvaluator,
                           metrics=SimpleNamespace(HOTA=lambda: object(), CLEAR=lambda: object(), Identity=lambda: object()))


def test_fake_trackeval_extracts_arrays_and_metrics(tmp_path):
    paths, seqs, _, _ = fixtures(tmp_path, include_empty=False)
    gt_root, trackers = make_mot_workspace(directory=tmp_path / "work", gt_csv=paths["gt"],
        sequence_csv=paths["sequences"], split="val", benchmark="SalmonVision", tracker="botsort",
        selected={"fish-a": seqs[0]}, predictions={})
    scores, combined = trackeval_metrics(gt_root=gt_root, tracker_root=trackers,
        output_root=tmp_path / "scores", benchmark="SalmonVision", split="val", tracker="botsort",
        selected={"fish-a": seqs[0]}, trackeval_module=fake_trackeval())
    assert combined["HOTA"] == pytest.approx(.7)
    assert combined["DetA"] == pytest.approx(.8)
    assert scores[0]["IDF1"] == .8


def test_end_to_end_trackeval_with_injected_parquet(tmp_path, monkeypatch):
    from object_detection.tracking_eval import eval_common
    paths, seqs, _, _ = fixtures(tmp_path, include_empty=False)
    def iter_rows(_):
        for n, x in enumerate((10, 60)):
            yield dict(split="val", video_stem="fish-a", frame_idx=n, mot_frame=n+1,
                       track_id=1, class_id=0, confidence=.8,
                       x_px=x, y_px=10, width_px=15, height_px=10)
    monkeypatch.setattr(eval_common, "iter_parquet_predictions", iter_rows)
    summary = evaluate_tracking(gt_csv=paths["gt"], sequence_csv=paths["sequences"],
        inference_status_csv=paths["status"], predictions_parquet=tmp_path / "placeholder.parquet",
        split="val", benchmark="SalmonVision", tracker="botsort", workdir_root=tmp_path / "tmp",
        summary_json=tmp_path / "summary.json", per_sequence_csv=tmp_path / "per.csv",
        coverage_csv_out=tmp_path / "coverage.csv", backend=fake_trackeval())
    assert summary["sequences_evaluated"] == 1
    assert summary["metrics"]["HOTA"] == pytest.approx(.7)
    assert "PROVISIONAL" in summary["interpretation"]
    assert len(list((tmp_path / "tmp").iterdir())) == 0  # ephemeral cleanup
    assert json.loads((tmp_path / "summary.json").read_text())["metrics"]["IDF1"] == .8


def test_prediction_duplicates_rejected(tmp_path, monkeypatch):
    from object_detection.tracking_eval import eval_common
    paths, seqs, _, _ = fixtures(tmp_path, include_empty=False)
    row = dict(split="val", video_stem="fish-a", frame_idx=0, mot_frame=1,
               track_id=1, class_id=0, confidence=.8,
               x_px=10, y_px=10, width_px=15, height_px=10)
    monkeypatch.setattr(eval_common, "iter_parquet_predictions", lambda _: iter([row, row]))
    with pytest.raises(ValueError, match="Duplicate"):
        predictions_by_video(tmp_path / "dummy", split="val", selected={"fish-a": seqs[0]},
                             inference_status_csv=paths["status"])
