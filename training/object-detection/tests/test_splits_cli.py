import json
import sys

from object_detection.splits.cli import main


def test_splits_cli_smoke(tmp_path, monkeypatch):
    labels_root = tmp_path / "labels"
    out_dir = tmp_path / "splits"

    for video, frame, line in [
        ("HIRMD-tankeeah-jetson-0_20250714_012827_M", 10, "0 0.5 0.5 0.1 0.2\n"),
        ("HIRMD-tankeeah-jetson-0_20250715_012827_M", 11, "1 0.5 0.5 0.2 0.2\n"),
        ("SFC-bear-jetsonnx-0_20250912_011859_M", 20, "0 0.5 0.5 0.3 0.1\n"),
    ]:
        p = labels_root / video / f"frame_{frame:06d}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(line, encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--labels-root", str(labels_root),
            "--out-dir", str(out_dir),
            "--sites", "tankeeah", "bear",
            "--seed", "42",
            "--train-frac", "0.8",
            "--val-frac", "0.1",
            "--test-frac", "0.1",
        ],
    )

    main()

    assert (out_dir / "train.txt").exists()
    assert (out_dir / "val.txt").exists()
    assert (out_dir / "test.txt").exists()
    assert (out_dir / "group_assignments.csv").exists()
    assert (out_dir / "split_report.json").exists()

    report = json.loads((out_dir / "split_report.json").read_text(encoding="utf-8"))
    assert "splits" in report
