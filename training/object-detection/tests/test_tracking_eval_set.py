from pathlib import Path
import csv
import pytest

from object_detection.tracking_eval import eval_set


def write_manifest(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_metadata(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["video_stem", "site", "org", "device", "s3_key"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_make_tracking_eval_set_val_writes_split_and_split_video_dir(tmp_path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    manifest = tmp_path / "val.txt"
    write_manifest(manifest, [
        f"val/{stem}/frame_000010.jpg",
        f"val/{stem}/frame_000012.jpg",
    ])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [{
        "video_stem": stem,
        "site": "tankeeah",
        "org": "HIRMD",
        "device": "jetson-0",
        "s3_key": f"HIRMD/tankeeah/jetson-0/motion_vids/{stem}.mp4",
    }])

    out_csv = tmp_path / "val_videos.csv"
    videos_dir = tmp_path / "videos"
    records = eval_set.make_tracking_eval_set(
        manifest=manifest,
        split="val",
        metadata_csv=metadata,
        out_csv=out_csv,
        videos_dir=videos_dir,
    )

    assert len(records) == 1
    assert records[0].split == "val"
    assert records[0].n_manifest_frames == 2
    assert records[0].local_video_path == str(videos_dir / "val" / f"{stem}.mp4")

    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert rows[0]["split"] == "val"
    assert rows[0]["video_stem"] == stem
    assert rows[0]["n_manifest_frames"] == "2"
    assert rows[0]["local_video_path"] == str(videos_dir / "val" / f"{stem}.mp4")


def test_tracking_eval_set_detects_video_level_leakage(tmp_path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    val_manifest = tmp_path / "val.txt"
    train_manifest = tmp_path / "train.txt"
    write_manifest(val_manifest, [f"val/{stem}/frame_000010.jpg"])
    write_manifest(train_manifest, [f"train/{stem}/frame_000030.jpg"])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [])

    with pytest.raises(RuntimeError, match="Tracking split leakage detected"):
        eval_set.make_tracking_eval_set(
            manifest=val_manifest,
            split="val",
            metadata_csv=metadata,
            out_csv=tmp_path / "out.csv",
            videos_dir=tmp_path / "videos",
            compare_manifests=[("train", train_manifest)],
        )


def test_leakage_check_happens_before_max_videos_subset(tmp_path):
    stem_a = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    stem_b = "HIRMD-tankeeah-jetson-0_20250715_012827_M"
    val_manifest = tmp_path / "val.txt"
    test_manifest = tmp_path / "test.txt"
    write_manifest(val_manifest, [
        f"val/{stem_a}/frame_000010.jpg",
        f"val/{stem_b}/frame_000010.jpg",
    ])
    write_manifest(test_manifest, [f"test/{stem_b}/frame_000020.jpg"])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [])

    with pytest.raises(RuntimeError, match=stem_b):
        eval_set.make_tracking_eval_set(
            manifest=val_manifest,
            split="val",
            metadata_csv=metadata,
            out_csv=tmp_path / "out.csv",
            videos_dir=tmp_path / "videos",
            max_videos=1,
            compare_manifests=[("test", test_manifest)],
        )


def test_missing_metadata_uses_fallback_key(tmp_path):
    stem = "GWA-stephenssmolt-jetsonnx-1_20260615_131255_M"
    manifest = tmp_path / "test.txt"
    write_manifest(manifest, [f"test/{stem}/frame_000001.jpg"])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [])

    records = eval_set.make_tracking_eval_set(
        manifest=manifest,
        split="test",
        metadata_csv=metadata,
        out_csv=tmp_path / "out.csv",
        videos_dir=tmp_path / "videos",
    )

    assert records[0].metadata_found is False
    assert records[0].s3_key == (
        f"GWA/stephenssmolt/jetsonnx-1/motion_vids/{stem}.mp4"
    )


def test_require_metadata_rejects_missing_metadata(tmp_path):
    stem = "HIRMD-koeye-jetson-0_20250826_120113_M"
    manifest = tmp_path / "test.txt"
    write_manifest(manifest, [f"test/{stem}/frame_000001.jpg"])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [])

    with pytest.raises(RuntimeError, match="Missing metadata rows"):
        eval_set.make_tracking_eval_set(
            manifest=manifest,
            split="test",
            metadata_csv=metadata,
            out_csv=tmp_path / "out.csv",
            videos_dir=tmp_path / "videos",
            require_metadata=True,
        )


def test_invalid_split_and_negative_max_videos(tmp_path):
    manifest = tmp_path / "x.txt"
    metadata = tmp_path / "metadata.csv"
    write_manifest(manifest, ["test/HIRMD-koeye-jetson-0_20250826_120113_M/frame_000001.jpg"])
    write_metadata(metadata, [])

    with pytest.raises(ValueError, match="split must be"):
        eval_set.make_tracking_eval_set(
            manifest=manifest,
            split="train",
            metadata_csv=metadata,
            out_csv=tmp_path / "out.csv",
            videos_dir=tmp_path / "videos",
        )

    with pytest.raises(ValueError, match="max_videos"):
        eval_set.make_tracking_eval_set(
            manifest=manifest,
            split="test",
            metadata_csv=metadata,
            out_csv=tmp_path / "out.csv",
            videos_dir=tmp_path / "videos",
            max_videos=-1,
        )


def test_legacy_python_api_still_builds_test_split(tmp_path):
    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    manifest = tmp_path / "test.txt"
    write_manifest(manifest, [f"test/{stem}/frame_000010.jpg"])
    metadata = tmp_path / "metadata.csv"
    write_metadata(metadata, [])

    records = eval_set.make_tracking_test_set(
        test_manifest=manifest,
        metadata_csv=metadata,
        out_csv=tmp_path / "out.csv",
        videos_dir=tmp_path / "videos",
    )
    assert records[0].split == "test"


def test_leakage_check_ignores_current_split_manifest(tmp_path: Path):
    from object_detection.tracking_eval.eval_set import assert_no_video_overlap

    stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    val_manifest = tmp_path / "val.txt"
    val_manifest.write_text(
        f"val/{stem}/frame_000010.jpg\n",
        encoding="utf-8",
    )

    # Passing all split manifests uniformly from DVC is convenient; the helper
    # must ignore the current split rather than reporting self-overlap.
    assert_no_video_overlap(
        split="val",
        selected_video_stems=[stem],
        compare_manifests=[("val", val_manifest)],
    )
