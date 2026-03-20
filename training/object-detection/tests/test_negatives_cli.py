import json
import sys
from pathlib import Path

from object_detection.negatives.cli import main


def write_conditions_csv(path: Path):
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
    rows = [
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
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


class FakeBody:
    def __init__(self, payload: str):
        self.payload = payload.encode("utf-8")

    def read(self):
        return self.payload


class FakeS3Client:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, Bucket: str, Key: str):
        return {"Body": FakeBody(json.dumps(self.objects[Key]))}


class FakeSession:
    def __init__(self, objects):
        self.objects = objects

    def client(self, name: str):
        assert name == "s3"
        return FakeS3Client(self.objects)


def test_negatives_cli_smoke(tmp_path, monkeypatch):
    import object_detection.negatives.conditions as cond_mod

    csv_path = tmp_path / "conditions.csv"
    write_conditions_csv(csv_path)

    video_stem = "HIRMD-tankeeah-jetson-0_20250604_004242_M"
    task_item = {
        "id": 1,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_filename": f"{video_stem}.mp4",
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 30,
            "metadata_video_duration": 3.0,
            "frames_per_second": 10.0,
            "metadata_video_r_frame_rate": "10/1",
            "metadata_video_avg_frame_rate": "10/1",
            "video": f"s3://bucket/{video_stem}.mp4",
        },
        "annotations": [
            {
                "updated_at": "2025-03-01T03:49:36.058815Z",
                "result": [
                    {
                        "type": "videorectangle",
                        "from_name": "box",
                        "to_name": "video",
                        "value": {
                            "labels": ["Sockeye"],
                            "sequence": [
                                {"enabled": True, "frame": 10, "x": 10, "y": 20, "width": 30, "height": 40}
                            ],
                            "framesCount": 30,
                        },
                    }
                ],
            }
        ],
    }

    objects = {
        f"HIRMD/tankeeah/jetson-0/labelstudio_tasks/{video_stem}.json": [task_item]
    }

    monkeypatch.setattr(cond_mod.boto3, "Session", lambda profile_name=None: FakeSession(objects))
    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--conditions-csv", str(csv_path),
            "--out-dir", str(out_dir),
            "--frames-per-video", "3",
            "--frame-stride", "3",
            "--frame-offset-mode", "fixed",
            "--frame-offset", "0",
        ],
    )

    main()

    assert (out_dir / "condition_negative_manifest.csv").exists()
    assert (out_dir / "condition_negative_summary.json").exists()
    assert (out_dir / "condition_negatives-000000.tar").exists()
