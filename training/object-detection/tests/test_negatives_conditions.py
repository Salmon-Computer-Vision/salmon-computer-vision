import json
import tarfile
from pathlib import Path
from typing import Dict, List

import pytest

from object_detection.negatives.conditions import (
    DEFAULT_BUCKET,
    ConditionRow,
    active_condition_columns,
    compute_condition_targets,
    construct_task_s3_key,
    construct_video_stem,
    create_condition_negative_shards,
    eligible_negative_frames,
    extract_latest_results,
    extract_positive_frames,
    extract_task_item,
    greedy_select_balanced_rows,
    infer_condition_columns,
    infer_total_frames,
    interpolate_sequence,
    load_condition_rows,
    normalize_date,
    normalize_time,
    normalize_value,
    parse_ffmpeg_rate,
    parse_ts,
    sample_frames,
    stride_offset,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_conditions_csv(path: Path, rows: List[dict]) -> Path:
    import csv

    fieldnames = [
        "Project",
        "Site",
        "Camera",
        "Filename",
        "Date",
        "Time",
        "Turbidity (1-5)",
        "Debris (buildup within box 1-5)",
        "Algae (buildup on plexiglass (1-5))",
        "Lighting (1-5)",
        "Tidal (0/1)",
        "Camera orientation (Normal, vertical, horizontal) (0/1)",
        "Box above water",
        "Notes:",
        "Image Link:",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


def make_task_item(
    *,
    filename: str,
    site: str = "tankeeah",
    total_frames: int = 30,
    sequence=None,
    updated_at: str = "2025-03-01T03:49:36.058815Z",
):
    if sequence is None:
        sequence = [
            {"enabled": True, "frame": 10, "x": 10, "y": 20, "width": 30, "height": 40},
            {"enabled": True, "frame": 12, "x": 20, "y": 30, "width": 30, "height": 40},
        ]

    result = []
    if sequence is not None:
        result = [
            {
                "type": "videorectangle",
                "from_name": "box",
                "to_name": "video",
                "value": {
                    "labels": ["Sockeye"],
                    "sequence": sequence,
                    "framesCount": total_frames,
                },
            }
        ]

    return {
        "id": 1,
        "data": {
            "metadata_file_site_reference_string": site,
            "metadata_file_filename": filename,
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": total_frames,
            "metadata_video_duration": total_frames / 10.0,
            "frames_per_second": 10.0,
            "metadata_video_r_frame_rate": "10/1",
            "metadata_video_avg_frame_rate": "10/1",
            "video": f"s3://bucket/{filename}",
        },
        "annotations": [
            {
                "updated_at": updated_at,
                "result": result,
            }
        ],
    }


class FakeBody:
    def __init__(self, payload: str):
        self.payload = payload.encode("utf-8")

    def read(self):
        return self.payload


class FakeS3Client:
    def __init__(self, objects: Dict[str, object]):
        self.objects = objects

    def get_object(self, Bucket: str, Key: str):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": FakeBody(json.dumps(self.objects[Key]))}


class FakeSession:
    def __init__(self, objects: Dict[str, object]):
        self.objects = objects

    def client(self, name: str):
        assert name == "s3"
        return FakeS3Client(self.objects)


# ----------------------------
# Small helpers
# ----------------------------

def test_normalize_value():
    assert normalize_value(" 1 ") == "1"
    assert normalize_value("NA") is None
    assert normalize_value("") is None
    assert normalize_value(None) is None


def test_normalize_date():
    assert normalize_date("2025-06-04") == "20250604"


def test_normalize_time():
    assert normalize_time("3:17:05") == "031705"
    assert normalize_time("13:17:05") == "131705"


def test_construct_video_stem():
    got = construct_video_stem("HIRMD", "tankeeah", "jetson-1", "2025-06-04", "3:17:05")
    assert got == "HIRMD-tankeeah-jetson-1_20250604_031705_M"


def test_construct_task_s3_key():
    got = construct_task_s3_key(
        "HIRMD",
        "tankeeah",
        "jetson-1",
        "HIRMD-tankeeah-jetson-1_20250604_031705_M",
    )
    assert got == "HIRMD/tankeeah/jetson-1/labelstudio_tasks/HIRMD-tankeeah-jetson-1_20250604_031705_M.json"


def test_infer_condition_columns():
    fieldnames = [
        "Project",
        "Site",
        "Camera",
        "Filename",
        "Date",
        "Time",
        "Turbidity (1-5)",
        "Lighting (1-5)",
        "Notes:",
    ]
    got = infer_condition_columns(fieldnames)
    assert got == ["Turbidity (1-5)", "Lighting (1-5)"]


# ----------------------------
# CSV loading and balancing
# ----------------------------

def test_load_condition_rows(tmp_path: Path):
    csv_path = make_conditions_csv(
        tmp_path / "cond.csv",
        [
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-1",
                "Filename": "1233080",
                "Date": "2025-06-04",
                "Time": "3:17:05",
                "Turbidity (1-5)": "1",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "2",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            }
        ],
    )

    rows, cols = load_condition_rows([csv_path])

    assert len(rows) == 1
    assert rows[0].video_stem == "HIRMD-tankeeah-jetson-1_20250604_031705_M"
    assert rows[0].s3_key.endswith(".json")
    assert "Turbidity (1-5)" in cols
    assert rows[0].conditions["Lighting (1-5)"] == "2"


def test_load_condition_rows_skips_blank_or_na_rows(tmp_path: Path):
    csv_path = make_conditions_csv(
        tmp_path / "cond.csv",
        [
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-1",
                "Filename": "NA",
                "Date": "2025-06-04",
                "Time": "3:17:05",
                "Turbidity (1-5)": "1",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "2",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            }
        ],
    )

    rows, _ = load_condition_rows([csv_path])
    assert rows == []


def test_active_condition_columns():
    rows = [
        ConditionRow(
            project="HIRMD",
            site="tankeeah",
            camera="jetson-0",
            labelstudio_task_id="1",
            date="2025-06-04",
            time="3:17:05",
            video_stem="a",
            s3_key="a.json",
            conditions={"Turbidity (1-5)": "1", "Lighting (1-5)": "2"},
            source_csv="x.csv",
        ),
        ConditionRow(
            project="HIRMD",
            site="tankeeah",
            camera="jetson-0",
            labelstudio_task_id="2",
            date="2025-06-05",
            time="3:17:05",
            video_stem="b",
            s3_key="b.json",
            conditions={"Turbidity (1-5)": "2", "Lighting (1-5)": "2"},
            source_csv="x.csv",
        ),
    ]
    cols = active_condition_columns(rows, ["Turbidity (1-5)", "Lighting (1-5)"])
    assert cols == ["Turbidity (1-5)"]


def test_compute_condition_targets():
    rows = [
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "1", "2025-06-04", "3:17:05", "a", "a.json",
                     {"Turbidity (1-5)": "1", "Lighting (1-5)": "2"}, "x.csv"),
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "2", "2025-06-05", "3:17:05", "b", "b.json",
                     {"Turbidity (1-5)": "1", "Lighting (1-5)": "1"}, "x.csv"),
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "3", "2025-06-06", "3:17:05", "c", "c.json",
                     {"Turbidity (1-5)": "2", "Lighting (1-5)": "2"}, "x.csv"),
    ]
    targets, counts = compute_condition_targets(rows, ["Turbidity (1-5)", "Lighting (1-5)"])

    assert counts["Turbidity (1-5)"]["1"] == 2
    assert counts["Turbidity (1-5)"]["2"] == 1
    assert targets[("Turbidity (1-5)", "1")] == 1
    assert targets[("Turbidity (1-5)", "2")] == 1


def test_greedy_select_balanced_rows():
    rows = [
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "1", "2025-06-04", "3:17:05", "a", "a.json",
                     {"Turbidity (1-5)": "1", "Lighting (1-5)": "1"}, "x.csv"),
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "2", "2025-06-05", "3:17:05", "b", "b.json",
                     {"Turbidity (1-5)": "1", "Lighting (1-5)": "2"}, "x.csv"),
        ConditionRow("HIRMD", "tankeeah", "jetson-0", "3", "2025-06-06", "3:17:05", "c", "c.json",
                     {"Turbidity (1-5)": "2", "Lighting (1-5)": "2"}, "x.csv"),
    ]

    selected, targets, counts = greedy_select_balanced_rows(rows, ["Turbidity (1-5)", "Lighting (1-5)"])
    assert len(selected) >= 2
    assert ("Turbidity (1-5)", "1") in targets
    assert counts["Lighting (1-5)"]["2"] == 2


# ----------------------------
# Task JSON helpers
# ----------------------------

def test_parse_ts():
    dt = parse_ts("2025-03-01T03:49:36.058815Z")
    assert dt.year == 2025
    assert dt.month == 3
    assert dt.tzinfo is not None


def test_parse_ffmpeg_rate():
    assert parse_ffmpeg_rate("30000/1001") == pytest.approx(29.97002997)
    assert parse_ffmpeg_rate("10") == pytest.approx(10.0)
    assert parse_ffmpeg_rate("bad") == 0.0


def test_interpolate_sequence():
    seq = [
        {"enabled": True, "frame": 10, "x": 0, "y": 0, "width": 10, "height": 10},
        {"enabled": True, "frame": 12, "x": 20, "y": 20, "width": 10, "height": 10},
    ]
    out = interpolate_sequence(seq)
    assert sorted(out.keys()) == [10, 11, 12]
    assert out[11][0][0] == pytest.approx(10.0)


def test_extract_task_item_from_dict():
    item = make_task_item(filename="HIRMD-tankeeah-jetson-0_20250604_031705_M.mp4")
    got = extract_task_item(item, "HIRMD-tankeeah-jetson-0_20250604_031705_M")
    assert got["data"]["metadata_file_filename"].endswith(".mp4")


def test_extract_task_item_from_list_prefers_matching_stem():
    item1 = make_task_item(filename="A-tankeeah-jetson-0_20250604_031705_M.mp4")
    item2 = make_task_item(filename="HIRMD-tankeeah-jetson-0_20250604_031705_M.mp4")
    got = extract_task_item([item1, item2], "HIRMD-tankeeah-jetson-0_20250604_031705_M")
    assert got["data"]["metadata_file_filename"] == "HIRMD-tankeeah-jetson-0_20250604_031705_M.mp4"


def test_infer_total_frames_prefers_metadata_video_nb_frames():
    item = make_task_item(filename="x.mp4", total_frames=97)
    assert infer_total_frames(item) == 97


def test_infer_total_frames_falls_back_to_result_framescount():
    item = make_task_item(filename="x.mp4", total_frames=30)
    item["data"]["metadata_video_nb_frames"] = 0
    results = item["annotations"][0]["result"]
    assert infer_total_frames(item, results=results) == 30


def test_infer_total_frames_falls_back_to_duration_times_fps():
    item = make_task_item(filename="x.mp4", total_frames=30)
    item["data"]["metadata_video_nb_frames"] = 0
    item["annotations"][0]["result"][0]["value"].pop("framesCount", None)
    item["data"]["metadata_video_duration"] = 9.7
    item["data"]["frames_per_second"] = 10.0
    assert infer_total_frames(item, results=item["annotations"][0]["result"]) == 97


def test_extract_latest_results_filters_type_names():
    item = make_task_item(filename="x.mp4")
    item["annotations"].append(
        {
            "updated_at": "2025-03-02T03:49:36.058815Z",
            "result": [
                {
                    "type": "videorectangle",
                    "from_name": "box",
                    "to_name": "video",
                    "value": {"labels": ["Sockeye"], "sequence": []},
                },
                {
                    "type": "not_video",
                    "from_name": "box",
                    "to_name": "video",
                    "value": {},
                },
            ],
        }
    )

    got = extract_latest_results(item, result_type="videorectangle", from_name="box", to_name="video")
    assert len(got) == 1
    assert got[0]["type"] == "videorectangle"


def test_extract_positive_frames():
    item = make_task_item(filename="x.mp4")
    got = extract_positive_frames(item)
    assert got == {10, 11, 12}


def test_stride_offset_fixed():
    assert stride_offset("video", 3, "fixed", 1) == 1


def test_stride_offset_video_hash_is_deterministic():
    a = stride_offset("video_name", 3, "video_hash", 0)
    b = stride_offset("video_name", 3, "video_hash", 0)
    assert a == b
    assert 0 <= a < 3


def test_eligible_negative_frames():
    got = eligible_negative_frames(
        "video",
        total_frames=10,
        positive_frames={0, 3, 6},
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
    )
    assert got == [9]


def test_sample_frames_is_deterministic():
    eligible = list(range(20))
    a = sample_frames("video", eligible, 5, seed=42)
    b = sample_frames("video", eligible, 5, seed=42)
    assert a == b
    assert len(a) == 5


# ----------------------------
# End-to-end create_condition_negative_shards
# ----------------------------

def test_create_condition_negative_shards(tmp_path: Path, monkeypatch):
    csv_path = make_conditions_csv(
        tmp_path / "conditions.csv",
        [
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-0",
                "Filename": "1233905",
                "Date": "2025-06-04",
                "Time": "0:42:42",
                "Turbidity (1-5)": "1",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "2",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            },
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-1",
                "Filename": "1233088",
                "Date": "2025-06-04",
                "Time": "8:22:39",
                "Turbidity (1-5)": "2",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "1",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            },
        ],
    )

    video_stem_a = "HIRMD-tankeeah-jetson-0_20250604_004242_M"
    video_stem_b = "HIRMD-tankeeah-jetson-1_20250604_082239_M"

    objects = {
        f"HIRMD/tankeeah/jetson-0/labelstudio_tasks/{video_stem_a}.json": [
            make_task_item(filename=f"{video_stem_a}.mp4", total_frames=30, sequence=[{"enabled": True, "frame": 10, "x": 10, "y": 20, "width": 30, "height": 40}])
        ],
        f"HIRMD/tankeeah/jetson-1/labelstudio_tasks/{video_stem_b}.json": [
            make_task_item(filename=f"{video_stem_b}.mp4", total_frames=30, sequence=[{"enabled": True, "frame": 12, "x": 10, "y": 20, "width": 30, "height": 40}])
        ],
    }

    import object_detection.negatives.conditions as cond_mod

    monkeypatch.setattr(cond_mod.boto3, "Session", lambda profile_name=None: FakeSession(objects))

    out_dir = tmp_path / "out"
    summary = create_condition_negative_shards(
        csv_paths=[csv_path],
        out_dir=out_dir,
        frames_per_video=5,
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
        shard_size=1000,
        negative_seed=42,
    )

    assert summary["input_rows"] == 2
    assert summary["written_videos"] >= 1
    assert summary["written_negative_frames"] >= 1

    manifest = out_dir / "condition_negative_manifest.csv"
    report = out_dir / "condition_negative_summary.json"
    shard = out_dir / "condition_negatives-000000.tar"

    assert manifest.exists()
    assert report.exists()
    assert shard.exists()

    with tarfile.open(shard, "r") as tf:
        names = tf.getnames()
        assert len(names) >= 1
        for name in names:
            content = tf.extractfile(name).read().decode("utf-8")
            assert content == ""


def test_create_condition_negative_shards_handles_missing_s3_object(tmp_path: Path, monkeypatch):
    csv_path = make_conditions_csv(
        tmp_path / "conditions.csv",
        [
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-0",
                "Filename": "1233905",
                "Date": "2025-06-04",
                "Time": "0:42:42",
                "Turbidity (1-5)": "1",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "2",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            }
        ],
    )

    import object_detection.negatives.conditions as cond_mod
    monkeypatch.setattr(cond_mod.boto3, "Session", lambda profile_name=None: FakeSession({}))

    out_dir = tmp_path / "out"
    summary = create_condition_negative_shards(
        csv_paths=[csv_path],
        out_dir=out_dir,
        frames_per_video=5,
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
    )

    assert summary["written_videos"] == 0
    assert len(summary["failures"]) == 1
    assert (out_dir / "condition_negative_summary.json").exists()


def test_create_condition_negative_shards_respects_from_to_name(tmp_path: Path, monkeypatch):
    csv_path = make_conditions_csv(
        tmp_path / "conditions.csv",
        [
            {
                "Project": "HIRMD",
                "Site": "tankeeah",
                "Camera": "jetson-0",
                "Filename": "1233905",
                "Date": "2025-06-04",
                "Time": "0:42:42",
                "Turbidity (1-5)": "1",
                "Debris (buildup within box 1-5)": "1",
                "Algae (buildup on plexiglass (1-5))": "1",
                "Lighting (1-5)": "2",
                "Tidal (0/1)": "0",
                "Camera orientation (Normal, vertical, horizontal) (0/1)": "Normal",
                "Box above water": "0",
                "Notes:": "",
                "Image Link:": "",
            }
        ],
    )

    video_stem = "HIRMD-tankeeah-jetson-0_20250604_004242_M"
    item = make_task_item(filename=f"{video_stem}.mp4", total_frames=30)
    item["annotations"][0]["result"] = [
        {
            "type": "videorectangle",
            "from_name": "other",
            "to_name": "video",
            "value": {"labels": ["Sockeye"], "sequence": [{"enabled": True, "frame": 9, "x": 10, "y": 20, "width": 30, "height": 40}]},
        }
    ]

    objects = {
        f"HIRMD/tankeeah/jetson-0/labelstudio_tasks/{video_stem}.json": [item]
    }

    import object_detection.negatives.conditions as cond_mod
    monkeypatch.setattr(cond_mod.boto3, "Session", lambda profile_name=None: FakeSession(objects))

    out_dir = tmp_path / "out"
    summary = create_condition_negative_shards(
        csv_paths=[csv_path],
        out_dir=out_dir,
        frames_per_video=3,
        frame_stride=3,
        frame_offset_mode="fixed",
        frame_offset=0,
        from_name="box",
        to_name="video",
    )

    # Since the only annotation is filtered out, all stride-compatible frames are eligible negatives
    assert summary["written_videos"] == 1
    assert summary["written_negative_frames"] == 3
