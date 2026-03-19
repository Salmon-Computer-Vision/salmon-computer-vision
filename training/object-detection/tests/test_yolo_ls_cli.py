import json
import sys

from object_detection.yolo_ls.cli import main


def test_yolo_ls_cli_smoke(tmp_path, monkeypatch):
    yaml_path = tmp_path / "data.yaml"
    yaml_path.write_text("names: [Sockeye]\n", encoding="utf-8")

    item = {
        "id": 1,
        "data": {
            "metadata_file_site_reference_string": "tankeeah",
            "metadata_file_filename": "HIRMD-tankeeah-jetson-0_20240704_055747_M.mp4",
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 30,
            "video": "s3://bucket/HIRMD-tankeeah-jetson-0_20240704_055747_M.mp4",
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
                                {"enabled": True, "frame": 10, "x": 10, "y": 20, "width": 30, "height": 40},
                                {"enabled": True, "frame": 12, "x": 20, "y": 30, "width": 30, "height": 40},
                            ],
                        },
                    }
                ],
            }
        ],
    }

    json_dir = tmp_path / "jsons"
    json_dir.mkdir()
    (json_dir / "a.json").write_text(json.dumps([item]), encoding="utf-8")

    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            str(json_dir),
            "--data-yaml", str(yaml_path),
            "--out", str(out_dir),
            "--pattern", "*.json",
            "--coord-mode", "percent",
        ],
    )

    main()

    assert (out_dir / "HIRMD-tankeeah-jetson-0_20240704_055747_M" / "frame_000010.txt").exists()
