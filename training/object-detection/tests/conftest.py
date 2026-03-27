import json
from pathlib import Path

import pytest


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_ls_item(
    *,
    item_id=1,
    site="tankeeah",
    filename="HIRMD-tankeeah-jetson-0_20240704_055747_M.mp4",
    updated_at="2025-03-01T03:49:36.058815Z",
    labels=("Sockeye",),
    sequence=None,
    result_type="videorectangle",
    from_name="box",
    to_name="video",
    include_result=True,
    metadata_video_nb_frames=30,
):
    if sequence is None:
        sequence = [
            {"enabled": True, "frame": 10, "x": 10, "y": 20, "width": 30, "height": 40},
            {"enabled": True, "frame": 12, "x": 20, "y": 30, "width": 30, "height": 40},
        ]

    result = []
    if include_result:
        result = [
            {
                "type": result_type,
                "from_name": from_name,
                "to_name": to_name,
                "value": {
                    "labels": list(labels),
                    "sequence": sequence,
                    "framesCount": metadata_video_nb_frames,
                },
            }
        ]

    return {
        "id": item_id,
        "data": {
            "metadata_file_site_reference_string": site,
            "metadata_file_filename": filename,
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": metadata_video_nb_frames,
            "metadata_video_duration": metadata_video_nb_frames / 10.0,
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


def make_label_file(root: Path, video_stem: str, frame_idx: int, lines: str) -> Path:
    path = root / video_stem / f"frame_{frame_idx:06d}.txt"
    write_text(path, lines)
    return path


@pytest.fixture
def make_label_file_fixture():
    return make_label_file


@pytest.fixture
def sample_item():
    return make_ls_item()


@pytest.fixture
def sample_json_file(tmp_path, sample_item):
    p = tmp_path / "input.json"
    p.write_text(json.dumps([sample_item]), encoding="utf-8")
    return p
