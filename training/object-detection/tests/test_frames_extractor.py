import csv
import tarfile
from pathlib import Path

import pytest

from object_detection.frames.extractor import (
    ensure_dir,
    load_video_metadata_index,
    load_split_requests,
    merge_video_metadata_csvs,
    pack_split_dataset_shards,
    read_label_text,
    read_split_manifest,
    write_data_yaml,
    write_split_manifests,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_metadata_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_split_manifest_file(path: Path, lines):
    write_text(path, "\n".join(lines) + "\n")


def make_label_file(labels_root: Path, video_stem: str, frame_idx: int, text: str):
    p = labels_root / video_stem / f"frame_{frame_idx:06d}.txt"
    write_text(p, text)
    return p


def test_ensure_dir(tmp_path: Path):
    out = tmp_path / "a" / "b"
    ensure_dir(out)
    assert out.exists()
    assert out.is_dir()


def test_read_split_manifest(tmp_path: Path):
    p = tmp_path / "train.txt"
    write_text(p, "\nfoo\n\nbar \n")
    assert read_split_manifest(p) == ["foo", "bar"]


def test_write_split_manifests(tmp_path: Path):
    manifests_root = tmp_path / "manifests"
    write_split_manifests(
        manifests_root,
        {
            "train": ["train/z.jpg", "train/a.jpg"],
            "val": ["val/x.jpg"],
        },
    )
    assert (manifests_root / "train.txt").read_text(encoding="utf-8") == "train/a.jpg\ntrain/z.jpg\n"
    assert (manifests_root / "val.txt").read_text(encoding="utf-8") == "val/x.jpg\n"


def test_write_data_yaml(tmp_path: Path):
    manifests_root = tmp_path / "manifests"
    manifests_root.mkdir(parents=True, exist_ok=True)
    write_data_yaml(manifests_root, ["Sockeye", "Coho"])

    text = (manifests_root / "data.yaml").read_text(encoding="utf-8")
    assert "train:" in text
    assert "val:" in text
    assert "test:" in text
    assert "0: Sockeye" in text
    assert "1: Coho" in text


def test_load_video_metadata_index(tmp_path: Path):
    csv_path = tmp_path / "meta.csv"
    write_metadata_csv(
        csv_path,
        [
            {
                "video_stem": "A_20250101_000000_M",
                "fps": "10",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": "HIRMD/tankeeah/jetson-0/motion_vids/A_20250101_000000_M.mp4",
            }
        ],
    )
    got = load_video_metadata_index(csv_path)
    assert got["A_20250101_000000_M"]["fps"] == "10"


def test_merge_video_metadata_csvs_later_wins(tmp_path: Path):
    csv1 = tmp_path / "meta1.csv"
    csv2 = tmp_path / "meta2.csv"

    write_metadata_csv(
        csv1,
        [
            {
                "video_stem": "A_20250101_000000_M",
                "fps": "10",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": "old/key.mp4",
            }
        ],
    )
    write_metadata_csv(
        csv2,
        [
            {
                "video_stem": "A_20250101_000000_M",
                "fps": "30",
                "nb_frames": "300",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": "new/key.mp4",
            }
        ],
    )

    got = merge_video_metadata_csvs([csv1, csv2])
    assert got["A_20250101_000000_M"]["fps"] == "30"
    assert got["A_20250101_000000_M"]["s3_key"] == "new/key.mp4"


def test_load_split_requests(tmp_path: Path):
    splits_dir = tmp_path / "splits"
    write_split_manifest_file(
        splits_dir / "train.txt",
        [
            "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000010.txt",
            "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000012.txt",
            "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000010.txt",
            "HIRMD-bear-jetsonnx-0_20250912_011859_M/frame_000020.txt",
        ],
    )

    got = load_split_requests(splits_dir, ["train", "val"])
    assert sorted(got["train"].keys()) == [
        "HIRMD-bear-jetsonnx-0_20250912_011859_M",
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
    ]
    assert got["train"]["HIRMD-tankeeah-jetson-0_20250714_012827_M"] == [10, 12]
    assert "val" not in got


def test_read_label_text(tmp_path: Path):
    labels_root = tmp_path / "labels"
    make_label_file(
        labels_root,
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
        10,
        "0 0.5 0.5 0.1 0.2\n",
    )
    got = read_label_text(
        labels_root,
        "HIRMD-tankeeah-jetson-0_20250714_012827_M/frame_000010.txt",
    )
    assert got == "0 0.5 0.5 0.1 0.2\n"


def test_pack_split_dataset_shards_happy_path(tmp_path: Path, monkeypatch):
    # Layout
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"
    build_manifest = tmp_path / "build_manifest.csv"

    video_stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"

    write_split_manifest_file(
        splits_dir / "train.txt",
        [
            f"{video_stem}/frame_000010.txt",
            f"{video_stem}/frame_000012.txt",
        ],
    )

    make_label_file(labels_root, video_stem, 10, "0 0.5 0.5 0.1 0.2\n")
    make_label_file(labels_root, video_stem, 12, "1 0.4 0.4 0.2 0.2\n")

    write_metadata_csv(
        metadata_csv,
        [
            {
                "video_stem": video_stem,
                "fps": "10",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": f"HIRMD/tankeeah/jetson-0/motion_vids/{video_stem}.mp4",
            }
        ],
    )

    # Fake download: just create a placeholder file
    def fake_download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    # Fake ffmpeg extraction: return deterministic bytes
    def fake_extract_frame_bytes_ffmpeg(video_path: Path, frame_idx: int, fps: float, image_ext: str = ".jpg") -> bytes:
        return f"fake-image-{frame_idx}-{fps}-{image_ext}".encode("utf-8")

    import object_detection.frames.extractor as extractor_mod

    monkeypatch.setattr(extractor_mod, "download_s3_video", fake_download_s3_video)
    monkeypatch.setattr(extractor_mod, "extract_frame_bytes_ffmpeg", fake_extract_frame_bytes_ffmpeg)

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=shards_root,
        manifests_root=manifests_root,
        temp_video_dir=temp_video_dir,
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye", "Coho"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
        image_ext=".jpg",
        cleanup_video=True,
        split_names=("train", "val", "test"),
        manifest_csv=build_manifest,
        shard_size=100,
    )

    assert stats.splits_seen == 1
    assert stats.videos_seen == 1
    assert stats.videos_processed == 1
    assert stats.videos_failed == 0
    assert stats.frames_requested == 2
    assert stats.images_written == 2
    assert stats.labels_written == 2

    # Temp video cleaned up
    assert not (temp_video_dir / f"{video_stem}.mp4").exists()

    # Shard exists and contains both image + label members
    shard_path = shards_root / "train-000000.tar"
    assert shard_path.exists()

    with tarfile.open(shard_path, "r") as tf:
        names = sorted(tf.getnames())
        assert f"train/{video_stem}/frame_000010.jpg" in names
        assert f"train/{video_stem}/frame_000010.txt" in names
        assert f"train/{video_stem}/frame_000012.jpg" in names
        assert f"train/{video_stem}/frame_000012.txt" in names

        label_10 = tf.extractfile(f"train/{video_stem}/frame_000010.txt").read().decode("utf-8")
        assert label_10 == "0 0.5 0.5 0.1 0.2\n"

        image_12 = tf.extractfile(f"train/{video_stem}/frame_000012.jpg").read()
        assert image_12 == b"fake-image-12-10.0-.jpg"

    # New packed manifests
    assert (manifests_root / "train.txt").read_text(encoding="utf-8") == (
        f"train/{video_stem}/frame_000010.jpg\n"
        f"train/{video_stem}/frame_000012.jpg\n"
    )
    assert (manifests_root / "data.yaml").exists()

    # Build manifest CSV
    rows = list(csv.DictReader(build_manifest.open("r", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["split"] == "train"
    assert rows[0]["video_stem"] == video_stem
    assert rows[0]["requested_frames"] == "2"
    assert rows[0]["images_written"] == "2"
    assert rows[0]["labels_written"] == "2"
    assert rows[0]["status"] == "ok"


def test_pack_split_dataset_shards_missing_metadata(tmp_path: Path, monkeypatch):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"
    build_manifest = tmp_path / "build_manifest.csv"

    video_stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"

    write_split_manifest_file(
        splits_dir / "train.txt",
        [f"{video_stem}/frame_000010.txt"],
    )
    make_label_file(labels_root, video_stem, 10, "0 0.5 0.5 0.1 0.2\n")

    # Empty metadata file
    write_metadata_csv(metadata_csv, [])

    import object_detection.frames.extractor as extractor_mod

    def fake_download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
        raise AssertionError("download_s3_video should not be called when metadata is missing")

    monkeypatch.setattr(extractor_mod, "download_s3_video", fake_download_s3_video)

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=shards_root,
        manifests_root=manifests_root,
        temp_video_dir=temp_video_dir,
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
        manifest_csv=build_manifest,
    )

    assert stats.videos_seen == 1
    assert stats.videos_processed == 0
    assert stats.videos_failed == 1
    assert stats.frames_requested == 1
    assert stats.images_written == 0
    assert stats.labels_written == 0

    rows = list(csv.DictReader(build_manifest.open("r", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert "Missing metadata" in rows[0]["error"]


def test_pack_split_dataset_shards_invalid_fps(tmp_path: Path, monkeypatch):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"

    video_stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"

    write_split_manifest_file(
        splits_dir / "train.txt",
        [f"{video_stem}/frame_000010.txt"],
    )
    make_label_file(labels_root, video_stem, 10, "0 0.5 0.5 0.1 0.2\n")

    write_metadata_csv(
        metadata_csv,
        [
            {
                "video_stem": video_stem,
                "fps": "0",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": "some/key.mp4",
            }
        ],
    )

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=shards_root,
        manifests_root=manifests_root,
        temp_video_dir=temp_video_dir,
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
    )

    assert stats.videos_failed == 1
    assert stats.images_written == 0
    assert stats.labels_written == 0


def test_pack_split_dataset_shards_fallback_to_bucket_plus_stem(tmp_path: Path, monkeypatch):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"

    video_stem = "HIRMD-tankeeah-jetson-0_20250714_012827_M"

    write_split_manifest_file(
        splits_dir / "train.txt",
        [f"{video_stem}/frame_000010.txt"],
    )
    make_label_file(labels_root, video_stem, 10, "0 0.5 0.5 0.1 0.2\n")

    write_metadata_csv(
        metadata_csv,
        [
            {
                "video_stem": video_stem,
                "fps": "10",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": "",
            }
        ],
    )

    captured = {}

    def fake_download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
        captured["bucket"] = bucket
        captured["s3_key"] = s3_key
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    def fake_extract_frame_bytes_ffmpeg(video_path: Path, frame_idx: int, fps: float, image_ext: str = ".jpg") -> bytes:
        return b"img"

    import object_detection.frames.extractor as extractor_mod

    monkeypatch.setattr(extractor_mod, "download_s3_video", fake_download_s3_video)
    monkeypatch.setattr(extractor_mod, "extract_frame_bytes_ffmpeg", fake_extract_frame_bytes_ffmpeg)

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=shards_root,
        manifests_root=manifests_root,
        temp_video_dir=temp_video_dir,
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
    )

    assert stats.videos_processed == 1
    assert captured["bucket"] == "prod-salmonvision-edge-assets-labelstudio-source"
    assert captured["s3_key"] == (
        "HIRMD/tankeeah/jetson-0/motion_vids/HIRMD-tankeeah-jetson-0_20250714_012827_M.mp4"
    )


def test_pack_split_dataset_shards_multiple_splits(tmp_path: Path, monkeypatch):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"

    train_video = "HIRMD-tankeeah-jetson-0_20250714_012827_M"
    val_video = "HIRMD-bear-jetsonnx-0_20250912_011859_M"

    write_split_manifest_file(splits_dir / "train.txt", [f"{train_video}/frame_000010.txt"])
    write_split_manifest_file(splits_dir / "val.txt", [f"{val_video}/frame_000020.txt"])

    make_label_file(labels_root, train_video, 10, "0 0.5 0.5 0.1 0.2\n")
    make_label_file(labels_root, val_video, 20, "1 0.4 0.4 0.2 0.2\n")

    write_metadata_csv(
        metadata_csv,
        [
            {
                "video_stem": train_video,
                "fps": "10",
                "nb_frames": "100",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "tankeeah",
                "device": "jetson-0",
                "s3_key": f"HIRMD/tankeeah/jetson-0/motion_vids/{train_video}.mp4",
            },
            {
                "video_stem": val_video,
                "fps": "30",
                "nb_frames": "300",
                "duration": "10.0",
                "width": "1280",
                "height": "720",
                "org": "HIRMD",
                "site": "bear",
                "device": "jetsonnx-0",
                "s3_key": f"HIRMD/bear/jetsonnx-0/motion_vids/{val_video}.mp4",
            },
        ],
    )

    def fake_download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    def fake_extract_frame_bytes_ffmpeg(video_path: Path, frame_idx: int, fps: float, image_ext: str = ".jpg") -> bytes:
        return f"{video_path.stem}:{frame_idx}:{fps}".encode("utf-8")

    import object_detection.frames.extractor as extractor_mod

    monkeypatch.setattr(extractor_mod, "download_s3_video", fake_download_s3_video)
    monkeypatch.setattr(extractor_mod, "extract_frame_bytes_ffmpeg", fake_extract_frame_bytes_ffmpeg)

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=shards_root,
        manifests_root=manifests_root,
        temp_video_dir=temp_video_dir,
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye", "Coho"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
    )

    assert stats.splits_seen == 2
    assert stats.videos_seen == 2
    assert stats.videos_processed == 2
    assert stats.images_written == 2
    assert stats.labels_written == 2

    assert (shards_root / "train-000000.tar").exists()
    assert (shards_root / "val-000000.tar").exists()

    train_manifest = (manifests_root / "train.txt").read_text(encoding="utf-8")
    val_manifest = (manifests_root / "val.txt").read_text(encoding="utf-8")

    assert f"train/{train_video}/frame_000010.jpg" in train_manifest
    assert f"val/{val_video}/frame_000020.jpg" in val_manifest
