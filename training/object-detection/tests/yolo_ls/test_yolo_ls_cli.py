import json
import sys
from pathlib import Path

import pytest

from object_detection.yolo_ls.cli import main


def make_item(
    *,
    site: str = "tankeeah",
    filename: str = "HIRMD-tankeeah-jetson-0_20240704_055747_M.mp4",
):
    return {
        "id": 1,
        "data": {
            "metadata_file_site_reference_string": site,
            "metadata_file_filename": filename,
            "metadata_video_width": 1280,
            "metadata_video_height": 720,
            "metadata_video_nb_frames": 30,
            "video": f"s3://bucket/{filename}",
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
                                {
                                    "enabled": True,
                                    "frame": 10,
                                    "x": 10,
                                    "y": 20,
                                    "width": 30,
                                    "height": 40,
                                },
                                {
                                    "enabled": True,
                                    "frame": 12,
                                    "x": 20,
                                    "y": 30,
                                    "width": 30,
                                    "height": 40,
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }


def write_data_yaml(path: Path) -> None:
    path.write_text("names: [Sockeye]\n", encoding="utf-8")


def test_yolo_ls_cli_directory_input_smoke(tmp_path, monkeypatch):
    """Keep legacy directory input covered while manifest input becomes primary."""
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    json_dir = tmp_path / "jsons"
    json_dir.mkdir()
    (json_dir / "a.json").write_text(
        json.dumps([make_item()]),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            str(json_dir),
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(out_dir),
            "--pattern",
            "*.json",
            "--coord-mode",
            "percent",
        ],
    )

    main()

    assert (
        out_dir
        / "HIRMD-tankeeah-jetson-0_20240704_055747_M"
        / "frame_000010.txt"
    ).exists()


def test_yolo_ls_cli_manifest_smoke_filters_mixed_site_export(
    tmp_path,
    monkeypatch,
    capsys,
):
    """
    A site manifest can reference an export containing tasks from multiple sites.
    --include-sites must still restrict conversion to the requested site.
    """
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    raw_root = tmp_path / "raw"
    export_path = raw_root / "HIRMD" / "mixed" / "project.json"
    export_path.parent.mkdir(parents=True)

    tankeeah_item = make_item()
    bear_item = make_item(
        site="bear",
        filename="SFC-bear-jetsonnx-0_20250912_011859_M.mp4",
    )
    export_path.write_text(
        json.dumps([tankeeah_item, bear_item]),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "tankeeah.json"
    manifest_path.write_text(
        json.dumps(
            {
                "site": "tankeeah",
                "raw_root": str(raw_root),
                "files": [
                    {
                        "path": "HIRMD/mixed/project.json",
                        "sha256": "unused-by-converter",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--input-manifest",
            str(manifest_path),
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(out_dir),
            "--include-sites",
            "tankeeah",
            "--coord-mode",
            "percent",
        ],
    )

    main()

    stdout = capsys.readouterr().out
    assert "Converting 1 Label Studio export(s) from manifest" in stdout

    assert (
        out_dir
        / "HIRMD-tankeeah-jetson-0_20240704_055747_M"
        / "frame_000010.txt"
    ).exists()

    assert not (
        out_dir
        / "SFC-bear-jetsonnx-0_20250912_011859_M"
    ).exists()


def test_yolo_ls_cli_manifest_multiple_exports(tmp_path, monkeypatch, capsys):
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    raw_root = tmp_path / "raw"
    raw_root.mkdir()

    a = raw_root / "a.json"
    b = raw_root / "nested" / "b.json"
    b.parent.mkdir()

    a.write_text(
        json.dumps(
            [
                make_item(
                    filename="HIRMD-tankeeah-jetson-0_20240704_055747_M.mp4"
                )
            ]
        ),
        encoding="utf-8",
    )
    b.write_text(
        json.dumps(
            [
                make_item(
                    filename="HIRMD-tankeeah-jetson-1_20240704_055748_M.mp4"
                )
            ]
        ),
        encoding="utf-8",
    )

    # Deliberately reverse the paths. The manifest loader sorts deterministically.
    manifest_path = tmp_path / "tankeeah.json"
    manifest_path.write_text(
        json.dumps(
            {
                "site": "tankeeah",
                "raw_root": str(raw_root),
                "files": [
                    {"path": "nested/b.json"},
                    {"path": "a.json"},
                ],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--input-manifest",
            str(manifest_path),
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(out_dir),
            "--include-sites",
            "tankeeah",
            "--coord-mode",
            "percent",
        ],
    )

    main()

    stdout = capsys.readouterr().out
    assert "Converting 2 Label Studio export(s) from manifest" in stdout

    assert (
        out_dir
        / "HIRMD-tankeeah-jetson-0_20240704_055747_M"
        / "frame_000010.txt"
    ).exists()
    assert (
        out_dir
        / "HIRMD-tankeeah-jetson-1_20240704_055748_M"
        / "frame_000010.txt"
    ).exists()


def test_yolo_ls_cli_manifest_raw_root_override(tmp_path, monkeypatch):
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    actual_raw_root = tmp_path / "mounted_elsewhere"
    actual_raw_root.mkdir()

    export_path = actual_raw_root / "project.json"
    export_path.write_text(
        json.dumps([make_item()]),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "tankeeah.json"
    manifest_path.write_text(
        json.dumps(
            {
                "site": "tankeeah",
                "raw_root": "/original/machine/path/that/does/not/exist",
                "files": [{"path": "project.json"}],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--input-manifest",
            str(manifest_path),
            "--manifest-raw-root",
            str(actual_raw_root),
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(out_dir),
            "--coord-mode",
            "percent",
        ],
    )

    main()

    assert (
        out_dir
        / "HIRMD-tankeeah-jetson-0_20240704_055747_M"
        / "frame_000010.txt"
    ).exists()


def test_yolo_ls_cli_requires_input_or_manifest(tmp_path, monkeypatch, capsys):
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(tmp_path / "out"),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert "one of positional input or --input-manifest is required" in (
        capsys.readouterr().err
    )


def test_yolo_ls_cli_rejects_positional_input_and_manifest_together(
    tmp_path,
    monkeypatch,
    capsys,
):
    yaml_path = tmp_path / "data.yaml"
    write_data_yaml(yaml_path)

    input_dir = tmp_path / "jsons"
    input_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            str(input_dir),
            "--input-manifest",
            str(manifest_path),
            "--data-yaml",
            str(yaml_path),
            "--out",
            str(tmp_path / "out"),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert "positional input and --input-manifest are mutually exclusive" in (
        capsys.readouterr().err
    )
