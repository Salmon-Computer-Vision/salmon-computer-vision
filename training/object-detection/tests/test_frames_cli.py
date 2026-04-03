import csv
import sys
import tarfile
from pathlib import Path

from object_detection.frames.cli import load_class_names_from_yolo_yaml, main


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


def test_load_class_names_from_yolo_yaml_list(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    write_text(
        yaml_path,
        "names:\n"
        "  - Sockeye\n"
        "  - Coho\n",
    )
    got = load_class_names_from_yolo_yaml(yaml_path)
    assert got == ["Sockeye", "Coho"]


def test_load_class_names_from_yolo_yaml_dict(tmp_path: Path):
    yaml_path = tmp_path / "data.yaml"
    write_text(
        yaml_path,
        "names:\n"
        "  0: Sockeye\n"
        "  1: Coho\n",
    )
    got = load_class_names_from_yolo_yaml(yaml_path)
    assert got == ["Sockeye", "Coho"]


def test_frames_cli_smoke(tmp_path: Path, monkeypatch, capsys):
    splits_dir = tmp_path / "splits"
    labels_root = tmp_path / "labels"
    shards_root = tmp_path / "shards"
    manifests_root = tmp_path / "packed_manifests"
    temp_video_dir = tmp_path / "tmp_videos"
    metadata_csv = tmp_path / "video_metadata.csv"
    build_manifest = tmp_path / "build_manifest.csv"
    data_yaml = tmp_path / "salmon_yolo.yaml"

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

    write_text(
        data_yaml,
        "names:\n"
        "  0: Sockeye\n"
        "  1: Coho\n",
    )

    def fake_download_s3_video(bucket: str, s3_key: str, local_video_path: Path) -> None:
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"fake-video")

    def fake_extract_frame_bytes_ffmpeg(video_path: Path, frame_idx: int, fps: float, image_ext: str = ".jpg") -> bytes:
        return f"fake-image-{frame_idx}-{fps}-{image_ext}".encode("utf-8")

    import object_detection.frames.extractor as extractor_mod
    monkeypatch.setattr(extractor_mod, "download_s3_video", fake_download_s3_video)
    monkeypatch.setattr(extractor_mod, "extract_frame_bytes_ffmpeg", fake_extract_frame_bytes_ffmpeg)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--splits-dir", str(splits_dir),
            "--labels-root", str(labels_root),
            "--shards-root", str(shards_root),
            "--manifests-root", str(manifests_root),
            "--temp-video-dir", str(temp_video_dir),
            "--metadata-csv", str(metadata_csv),
            "--data-yaml", str(data_yaml),
            "--bucket", "prod-salmonvision-edge-assets-labelstudio-source",
            "--image-ext", ".jpg",
            "--manifest-csv", str(build_manifest),
            "--splits", "train", "val", "test",
            "--shard-size", "100",
        ],
    )

    main()

    out = capsys.readouterr().out
    assert "Done." in out
    assert "splits_seen=1" in out
    assert "videos_seen=1" in out
    assert "videos_processed=1" in out
    assert "videos_failed=0" in out
    assert "frames_requested=2" in out
    assert "images_written=2" in out
    assert "labels_written=2" in out

    shard_path = shards_root / "train-000000.tar"
    assert shard_path.exists()

    with tarfile.open(shard_path, "r") as tf:
        names = sorted(tf.getnames())
        assert f"train/{video_stem}/frame_000010.jpg" in names
        assert f"train/{video_stem}/frame_000010.txt" in names
        assert f"train/{video_stem}/frame_000012.jpg" in names
        assert f"train/{video_stem}/frame_000012.txt" in names

    assert (manifests_root / "train.txt").exists()
    assert (manifests_root / "data.yaml").exists()
    assert build_manifest.exists()

    train_manifest = (manifests_root / "train.txt").read_text(encoding="utf-8")
    assert train_manifest == (
        f"train/{video_stem}/frame_000010.jpg\n"
        f"train/{video_stem}/frame_000012.jpg\n"
    )

    rows = list(csv.DictReader(build_manifest.open("r", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["split"] == "train"
    assert rows[0]["status"] == "ok"
    assert rows[0]["images_written"] == "2"
    assert rows[0]["labels_written"] == "2"
