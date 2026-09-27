import csv
import threading
from pathlib import Path

import pytest

from object_detection.frames.extractor import pack_split_dataset_shards


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_metadata_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["video_stem", "fps", "s3_key"],
        )
        writer.writeheader()
        writer.writerows(rows)


def prepare_two_video_dataset(tmp_path: Path):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    metadata_csv = tmp_path / "metadata.csv"

    videos = [
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
        "HIRMD-tankeeah-jetson-0_20250714_012900_M",
    ]

    write_text(
        splits_dir / "train.txt",
        "\n".join(
            f"{video}/frame_000010.txt"
            for video in videos
        ) + "\n",
    )

    for video in videos:
        write_text(
            labels_root / video / "frame_000010.txt",
            "0 0.5 0.5 0.1 0.2\n",
        )

    write_metadata_csv(
        metadata_csv,
        [
            {
                "video_stem": video,
                "fps": "10",
                "s3_key": (
                    f"HIRMD/tankeeah/jetson-0/motion_vids/"
                    f"{video}.mp4"
                ),
            }
            for video in videos
        ],
    )

    return splits_dir, labels_root, metadata_csv, videos


def test_source_video_downloads_run_concurrently(
    tmp_path: Path,
    monkeypatch,
):
    (
        splits_dir,
        labels_root,
        metadata_csv,
        videos,
    ) = prepare_two_video_dataset(tmp_path)

    import object_detection.frames.extractor as extractor_mod

    # Both worker threads must arrive here before either can complete. If the
    # implementation becomes sequential, this barrier times out and the test
    # fails.
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_download_s3_video(
        bucket: str,
        s3_key: str,
        local_video_path: Path,
    ) -> None:
        nonlocal active, max_active

        with lock:
            active += 1
            max_active = max(max_active, active)

        barrier.wait(timeout=5)

        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

        with lock:
            active -= 1

    def fake_extract_frame_bytes_ffmpeg(
        video_path: Path,
        frame_idx: int,
        fps: float,
        image_ext: str = ".jpg",
    ) -> bytes:
        return f"{video_path.stem}:{frame_idx}".encode()

    monkeypatch.setattr(
        extractor_mod,
        "download_s3_video",
        fake_download_s3_video,
    )
    monkeypatch.setattr(
        extractor_mod,
        "extract_frame_bytes_ffmpeg",
        fake_extract_frame_bytes_ffmpeg,
    )

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=tmp_path / "shards",
        manifests_root=tmp_path / "manifests",
        temp_video_dir=tmp_path / "tmp_videos",
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
        download_workers=2,
    )

    assert max_active == 2

    assert stats.videos_seen == 2
    assert stats.videos_processed == 2
    assert stats.videos_failed == 0
    assert stats.videos_downloaded == 2
    assert stats.images_extracted == 2
    assert stats.images_reused == 0


def test_download_workers_one_remains_valid(
    tmp_path: Path,
    monkeypatch,
):
    (
        splits_dir,
        labels_root,
        metadata_csv,
        videos,
    ) = prepare_two_video_dataset(tmp_path)

    import object_detection.frames.extractor as extractor_mod

    download_calls = []

    def fake_download_s3_video(
        bucket: str,
        s3_key: str,
        local_video_path: Path,
    ) -> None:
        download_calls.append(s3_key)
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    monkeypatch.setattr(
        extractor_mod,
        "download_s3_video",
        fake_download_s3_video,
    )
    monkeypatch.setattr(
        extractor_mod,
        "extract_frame_bytes_ffmpeg",
        lambda **kwargs: b"jpg",
    )

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=tmp_path / "shards",
        manifests_root=tmp_path / "manifests",
        temp_video_dir=tmp_path / "tmp_videos",
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
        download_workers=1,
    )

    assert len(download_calls) == 2
    assert stats.videos_processed == 2
    assert stats.videos_failed == 0


def test_invalid_download_workers_rejected(tmp_path: Path):
    with pytest.raises(
        ValueError,
        match=r"download_workers must be >= 1",
    ):
        pack_split_dataset_shards(
            splits_dir=tmp_path / "splits",
            labels_root=tmp_path / "labels",
            shards_root=tmp_path / "shards",
            manifests_root=tmp_path / "manifests",
            temp_video_dir=tmp_path / "tmp_videos",
            metadata_csv_paths=[],
            class_names=["Sockeye"],
            bucket="bucket",
            download_workers=0,
        )


def test_one_parallel_download_failure_does_not_abort_other_video(
    tmp_path: Path,
    monkeypatch,
):
    (
        splits_dir,
        labels_root,
        metadata_csv,
        videos,
    ) = prepare_two_video_dataset(tmp_path)

    import object_detection.frames.extractor as extractor_mod

    def fake_download_s3_video(
        bucket: str,
        s3_key: str,
        local_video_path: Path,
    ) -> None:
        if videos[0] in s3_key:
            raise RuntimeError("simulated download failure")

        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    monkeypatch.setattr(
        extractor_mod,
        "download_s3_video",
        fake_download_s3_video,
    )
    monkeypatch.setattr(
        extractor_mod,
        "extract_frame_bytes_ffmpeg",
        lambda **kwargs: b"jpg",
    )

    stats = pack_split_dataset_shards(
        splits_dir=splits_dir,
        labels_root=labels_root,
        shards_root=tmp_path / "shards",
        manifests_root=tmp_path / "manifests",
        temp_video_dir=tmp_path / "tmp_videos",
        metadata_csv_paths=[metadata_csv],
        class_names=["Sockeye"],
        bucket="prod-salmonvision-edge-assets-labelstudio-source",
        download_workers=2,
    )

    assert stats.videos_seen == 2
    assert stats.videos_processed == 1
    assert stats.videos_failed == 1

    # Count only successful source-video downloads, matching the existing
    # semantics of ExtractionStats.videos_downloaded.
    assert stats.videos_downloaded == 1
