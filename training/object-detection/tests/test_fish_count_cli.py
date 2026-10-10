"""Regression test: CLI forwards every required evaluate_counts output path."""
from pathlib import Path

import object_detection.tracking_eval.count_metrics as mod


def test_cli_forwards_per_site_csv(monkeypatch, capsys):
    captured = {}

    def fake_evaluate_counts(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mod, "evaluate_counts", fake_evaluate_counts)
    mod.main([
        "--gt-csv", "gt.csv",
        "--sequences-csv", "sequences.csv",
        "--inference-status-csv", "inference.csv",
        "--predictions-parquet", "preds.parquet",
        "--data-yaml", "data.yaml",
        "--split", "val",
        "--summary-json", "summary.json",
        "--per-group-csv", "group.csv",
        "--per-video-csv", "video.csv",
        "--per-site-csv", "site.csv",
        "--events-csv", "events.csv",
        "--coverage-output-csv", "coverage.csv",
        "--annotation-scope", "verified",
        "--coverage-csv", "verified.csv",
    ])

    assert captured["per_site_csv"] == Path("site.csv")
    assert captured["per_group_csv"] == Path("group.csv")
    assert captured["per_video_csv"] == Path("video.csv")
    assert captured["coverage_csv_out"] == Path("coverage.csv")
    assert captured["scope"] == "verified"
    assert captured["coverage_csv"] == Path("verified.csv")
    assert "'ok': True" in capsys.readouterr().out
