import json
import tarfile
from pathlib import Path

import pytest

from object_detection.yolo_ls.converter import YoloConverterLSVideo


def test_stride_offset_fixed(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=2,
    )
    assert conv._stride_offset("video") == 2


def test_stride_offset_video_hash_deterministic(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=3,
        frame_offset_mode="video_hash",
    )
    a = conv._stride_offset("video_name")
    b = conv._stride_offset("video_name")
    assert a == b
    assert 0 <= a < 3


def test_stride_offset_invalid_mode(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=3,
        frame_offset_mode="bad_mode",
    )
    with pytest.raises(ValueError, match="Invalid frame offset mode"):
        conv._stride_offset("video")


def test_parse_ffmpeg_rate_fraction():
    assert YoloConverterLSVideo._parse_ffmpeg_rate("30000/1001") == pytest.approx(29.97002997)


def test_parse_ffmpeg_rate_float_string():
    assert YoloConverterLSVideo._parse_ffmpeg_rate("10.0") == pytest.approx(10.0)


def test_parse_ffmpeg_rate_bad():
    assert YoloConverterLSVideo._parse_ffmpeg_rate("not_a_rate") == 0.0


def test_infer_total_frames_prefers_metadata_video_nb_frames(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(class_map={"Sockeye": 0}, output_dir=tmp_path / "out")
    sample_item["data"]["metadata_video_nb_frames"] = 997
    assert conv._infer_total_frames(sample_item) == 997


def test_infer_total_frames_from_results_framescount(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(class_map={"Sockeye": 0}, output_dir=tmp_path / "out")
    sample_item["data"]["metadata_video_nb_frames"] = 0
    results = sample_item["annotations"][0]["result"]
    assert conv._infer_total_frames(sample_item, results=results) == 30


def test_infer_total_frames_from_duration_and_fps(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(class_map={"Sockeye": 0}, output_dir=tmp_path / "out")
    sample_item["data"]["metadata_video_nb_frames"] = 0
    sample_item["annotations"][0]["result"][0]["value"].pop("framesCount", None)
    sample_item["data"]["metadata_video_duration"] = 9.7
    sample_item["data"]["frames_per_second"] = 10.0
    assert conv._infer_total_frames(sample_item, results=sample_item["annotations"][0]["result"]) == 97


def test_eligible_frames_for_video_fixed_stride(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=1,
    )
    assert conv._eligible_frames_for_video("video", 10) == [1, 4, 7]


def test_sample_negative_frames_for_video_is_deterministic(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
        negative_seed=42,
    )
    a = conv._sample_negative_frames_for_video("video", 30, 4)
    b = conv._sample_negative_frames_for_video("video", 30, 4)
    assert a == b
    assert len(a) == 4
    assert all(f % 3 == 0 for f in a)


def test_interpolate_sequence_empty():
    assert YoloConverterLSVideo._interpolate_sequence([]) == {}


def test_interpolate_sequence_keyframes_and_interpolation():
    seq = [
        {"enabled": True, "frame": 10, "x": 0, "y": 0, "width": 10, "height": 10},
        {"enabled": True, "frame": 12, "x": 20, "y": 20, "width": 10, "height": 10},
    ]
    out = YoloConverterLSVideo._interpolate_sequence(seq)
    assert sorted(out.keys()) == [10, 11, 12]
    assert out[10] == [(0.0, 0.0, 10.0, 10.0)]
    assert out[12] == [(20.0, 20.0, 10.0, 10.0)]
    assert out[11][0][0] == pytest.approx(10.0)
    assert out[11][0][1] == pytest.approx(10.0)


def test_interpolate_sequence_disabled_start_no_forward_interpolation():
    seq = [
        {"enabled": False, "frame": 10, "x": 0, "y": 0, "width": 10, "height": 10},
        {"enabled": True, "frame": 12, "x": 20, "y": 20, "width": 10, "height": 10},
    ]
    out = YoloConverterLSVideo._interpolate_sequence(seq)
    assert sorted(out.keys()) == [10, 12]
    assert 11 not in out


def test_parse_ts():
    dt = YoloConverterLSVideo._parse_ts("2025-03-01T03:49:36.058815Z")
    assert dt.year == 2025
    assert dt.month == 3
    assert dt.tzinfo is not None


def test_log_error_writes_file(tmp_path: Path):
    log_path = tmp_path / "logs" / "err.log"
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        error_log_path=log_path,
    )
    conv._log_error("ctx", ValueError("boom"))
    text = log_path.read_text(encoding="utf-8")
    assert "ERROR in ctx" in text
    assert "ValueError: boom" in text


def test_convert_item_writes_filesystem_labels(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        coord_mode="percent",
    )
    stats = conv._convert_item(sample_item)

    assert stats.videos_with_boxes == 1
    assert stats.videos_without_boxes == 0
    assert stats.label_files_written == 3
    assert conv._positive_frame_files_written == 3

    out_file = tmp_path / "out" / "HIRMD-tankeeah-jetson-0_20240704_055747_M" / "frame_000010.txt"
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8").startswith("0 ")


def test_convert_item_respects_include_sites(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        include_sites=["bear"],
    )
    stats = conv._convert_item(sample_item)

    assert stats.videos_with_boxes == 0
    assert stats.videos_without_boxes == 0
    assert stats.label_files_written == 0


def test_convert_item_no_boxes_records_empty_video_and_negative_candidate(tmp_path: Path):
    empty_list = tmp_path / "empty.txt"
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        empty_list_path=empty_list,
        include_negatives=True,
    )

    item = {
        "id": 1,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_filename": "HIRMD-tankeeah-jetson-0_20240704_060000_M.mp4",
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 25,
            "metadata_video_duration": 2.5,
            "frames_per_second": 10.0,
            "video": "s3://bucket/HIRMD-tankeeah-jetson-0_20240704_060000_M.mp4",
        },
        "annotations": [
            {
                "updated_at": "2025-03-01T03:49:36.058815Z",
                "result": [],
            }
        ],
    }

    stats = conv._convert_item(item)

    assert stats.videos_with_boxes == 0
    assert stats.videos_without_boxes == 1
    assert stats.label_files_written == 0
    assert empty_list.read_text(encoding="utf-8").strip().endswith(".mp4")
    assert len(conv._negative_candidates) == 1
    assert conv._negative_candidates[0].total_frames == 25


def test_convert_item_respects_frame_stride(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        frame_stride=2,
        frame_offset_mode="fixed",
        frame_offset=0,
        coord_mode="percent",
    )
    stats = conv._convert_item(sample_item)

    assert stats.label_files_written == 2

    base = tmp_path / "out" / "HIRMD-tankeeah-jetson-0_20240704_055747_M"
    assert (base / "frame_000010.txt").exists()
    assert not (base / "frame_000011.txt").exists()
    assert (base / "frame_000012.txt").exists()


def test_convert_item_writes_to_shards(tmp_path: Path, sample_item):
    shard_dir = tmp_path / "shards"
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        shard_dir=shard_dir,
        shard_size=10,
        coord_mode="percent",
    )
    stats = conv._convert_item(sample_item)
    conv._sharder.close()

    assert stats.label_files_written == 3
    tar_path = shard_dir / "yolo_annos-000000.tar"
    assert tar_path.exists()

    with tarfile.open(tar_path, "r") as tf:
        names = sorted(tf.getnames())
        assert "HIRMD-tankeeah-jetson-0_20240704_055747_M/frame_000010.txt" in names
        content = tf.extractfile(
            "HIRMD-tankeeah-jetson-0_20240704_055747_M/frame_000010.txt"
        ).read().decode("utf-8")
        assert content.startswith("0 ")


def test_convert_item_skips_unknown_class(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Coho": 0},
        output_dir=tmp_path / "out",
    )
    stats = conv._convert_item(sample_item)

    assert stats.videos_with_boxes == 0
    assert stats.videos_without_boxes == 1
    assert stats.label_files_written == 0


def test_convert_file_happy_path(tmp_path: Path, sample_json_file):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        coord_mode="percent",
    )

    stats = conv.convert_file(sample_json_file)
    assert stats.videos_with_boxes == 1
    assert stats.videos_without_boxes == 0
    assert stats.label_files_written == 3
    assert stats.errors == 0


def test_convert_file_invalid_json(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
    )
    json_path = tmp_path / "bad.json"
    json_path.write_text("{not json", encoding="utf-8")

    stats = conv.convert_file(json_path)
    assert stats.errors == 1


def test_convert_file_top_level_not_list(tmp_path: Path):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
    )
    json_path = tmp_path / "bad.json"
    json_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    stats = conv.convert_file(json_path)
    assert stats.errors == 1


def test_convert_folder_reads_multiple_json_files(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        coord_mode="percent",
    )

    item1 = sample_item
    item2 = json.loads(json.dumps(sample_item))
    item2["data"]["metadata_file_filename"] = "HIRMD-tankeeah-jetson-0_20240704_055748_M.mp4"
    item2["data"]["video"] = "s3://bucket/HIRMD-tankeeah-jetson-0_20240704_055748_M.mp4"

    d = tmp_path / "jsons"
    d.mkdir()
    (d / "a.json").write_text(json.dumps([item1]), encoding="utf-8")
    (d / "b.json").write_text(json.dumps([item2]), encoding="utf-8")

    stats = conv.convert_folder(d, pattern="*.json")
    assert stats.videos_with_boxes == 2
    assert stats.label_files_written == 6
    assert stats.errors == 0


def test_materialize_negatives_writes_empty_files(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        include_negatives=True,
        negative_ratio=0.10,
        negatives_per_video=3,
        frame_stride=2,
        frame_offset_mode="fixed",
        frame_offset=0,
    )

    conv._convert_item(sample_item)

    empty_item = {
        "id": 2,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_filename": "HIRMD-tankeeah-jetson-0_20240704_060000_M.mp4",
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 20,
            "metadata_video_duration": 2.0,
            "frames_per_second": 10.0,
            "video": "s3://bucket/HIRMD-tankeeah-jetson-0_20240704_060000_M.mp4",
        },
        "annotations": [{"updated_at": "2025-03-01T03:49:36.058815Z", "result": []}],
    }
    conv._convert_item(empty_item)

    wrote, total_candidate_frames = conv.materialize_negatives()
    assert wrote == 0
    assert total_candidate_frames > 0


def test_materialize_negatives_with_enough_positives(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        include_negatives=True,
        negative_ratio=0.25,
        negatives_per_video=3,
        frame_stride=2,
        frame_offset_mode="fixed",
        frame_offset=0,
    )

    for i in range(4):
        item = json.loads(json.dumps(sample_item))
        item["id"] = i + 1
        item["data"]["metadata_file_filename"] = f"HIRMD-tankeeah-jetson-0_20240704_05574{i}_M.mp4"
        item["data"]["video"] = f"s3://bucket/HIRMD-tankeeah-jetson-0_20240704_05574{i}_M.mp4"
        conv._convert_item(item)

    for i in range(2):
        empty_item = {
            "id": 100 + i,
            "data": {
                "metadata_file_site_reference_string": "tankeeah",
                "metadata_file_filename": f"HIRMD-tankeeah-jetson-0_20240704_06100{i}_M.mp4",
                "metadata_video_width": 1280,
                "metadata_video_height": 720,
                "metadata_video_nb_frames": 20,
                "metadata_video_duration": 2.0,
                "frames_per_second": 10.0,
                "video": f"s3://bucket/HIRMD-tankeeah-jetson-0_20240704_06100{i}_M.mp4",
            },
            "annotations": [{"updated_at": "2025-03-01T03:49:36.058815Z", "result": []}],
        }
        conv._convert_item(empty_item)

    wrote, total_candidate_frames = conv.materialize_negatives()

    assert wrote == 4
    assert total_candidate_frames >= 4
    assert conv._negative_frame_files_written == 4

    txt_files = list((tmp_path / "out").rglob("frame_*.txt"))
    assert len(txt_files) >= 12 + 4


def test_materialize_negatives_writes_to_shards(tmp_path: Path, sample_item):
    conv = YoloConverterLSVideo(
        class_map={"Sockeye": 0},
        output_dir=tmp_path / "out",
        shard_dir=tmp_path / "shards",
        include_negatives=True,
        negative_ratio=0.50,
        negatives_per_video=2,
        frame_stride=1,
    )

    for i in range(2):
        item = json.loads(json.dumps(sample_item))
        item["id"] = i + 1
        item["data"]["metadata_file_filename"] = f"HIRMD-tankeeah-jetson-0_20240704_05570{i}_M.mp4"
        item["data"]["video"] = f"s3://bucket/HIRMD-tankeeah-jetson-0_20240704_05570{i}_M.mp4"
        conv._convert_item(item)

    empty_item = {
        "id": 3,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_filename": "HIRMD-tankeeah-jetson-0_20240704_070000_M.mp4",
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 10,
            "metadata_video_duration": 1.0,
            "frames_per_second": 10.0,
            "video": "s3://bucket/HIRMD-tankeeah-jetson-0_20240704_070000_M.mp4",
        },
        "annotations": [{"updated_at": "2025-03-01T03:49:36.058815Z", "result": []}],
    }
    conv._convert_item(empty_item)

    wrote, _ = conv.materialize_negatives()
    conv._sharder.close()

    assert wrote == 2

    tar_path = tmp_path / "shards" / "yolo_annos-000000.tar"
    with tarfile.open(tar_path, "r") as tf:
        negatives = [m for m in tf.getnames() if "20240704_070000" in m]
        assert len(negatives) == 2
        for name in negatives:
            content = tf.extractfile(name).read().decode("utf-8")
            assert content == ""
