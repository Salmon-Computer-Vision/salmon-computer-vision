import csv
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "merge_packed_site_datasets.py"
)


def load_cli_module():
    spec = importlib.util.spec_from_file_location(
        "merge_packed_site_datasets_script",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_site_dataset(
    sites_root: Path,
    site: str,
    *,
    video_stem: str,
) -> None:
    manifests = sites_root / site / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)

    for split in ("train", "val", "test"):
        write_text(
            manifests / f"{split}.txt",
            f"{split}/{video_stem}/frame_000001.jpg\n",
        )

    csv_path = sites_root / site / "packed_dataset_manifest.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "split",
                "video_stem",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "split": "train",
                "video_stem": video_stem,
                "status": "ok",
            }
        )


def test_merge_packed_site_datasets_cli_smoke(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    module = load_cli_module()

    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged_manifests"
    data_yaml = tmp_path / "salmon_yolo.yaml"
    params_yaml = tmp_path / "params.yaml"
    manifest_csv = tmp_path / "packed_dataset_manifest.csv"

    write_site_dataset(
        sites_root,
        "tankeeah",
        video_stem="HIRMD-tankeeah-jetson-0_20250714_012827_M",
    )
    write_site_dataset(
        sites_root,
        "bear",
        video_stem="SFC-bear-jetsonnx-0_20250912_011859_M",
    )

    write_text(
        data_yaml,
        yaml.safe_dump(
            {
                "names": {
                    0: "Sockeye",
                    1: "Coho",
                }
            },
            sort_keys=False,
        ),
    )

    write_text(
        params_yaml,
        yaml.safe_dump(
            {
                "data": {
                    "sites": [
                        "tankeeah",
                        "bear",
                    ]
                }
            },
            sort_keys=False,
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_packed_site_datasets.py",
            "--sites-root",
            str(sites_root),
            "--manifests-root",
            str(manifests_root),
            "--data-yaml",
            str(data_yaml),
            "--manifest-csv",
            str(manifest_csv),
            "--params-yaml",
            str(params_yaml),
        ],
    )

    module.main()

    out = capsys.readouterr().out

    assert "Merged 2 packed site datasets:" in out
    assert "  tankeeah" in out
    assert "  bear" in out

    assert (manifests_root / "train.txt").exists()
    assert (manifests_root / "val.txt").exists()
    assert (manifests_root / "test.txt").exists()
    assert (manifests_root / "data.yaml").exists()

    assert (manifests_root / "active_sites.txt").read_text(
        encoding="utf-8"
    ) == "tankeeah\nbear\n"

    with manifest_csv.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert [
        row["video_stem"]
        for row in rows
    ] == [
        "HIRMD-tankeeah-jetson-0_20250714_012827_M",
        "SFC-bear-jetsonnx-0_20250912_011859_M",
    ]


def test_merge_packed_site_datasets_cli_requires_sites_list(
    tmp_path: Path,
    monkeypatch,
):
    module = load_cli_module()

    params_yaml = tmp_path / "params.yaml"

    # This is intentionally the old whitespace-string style rather than
    # the YAML list required by the current foreach-based DVC pipeline.
    write_text(
        params_yaml,
        yaml.safe_dump(
            {
                "data": {
                    "sites": "tankeeah bear",
                }
            },
            sort_keys=False,
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_packed_site_datasets.py",
            "--sites-root",
            str(tmp_path / "sites"),
            "--manifests-root",
            str(tmp_path / "manifests"),
            "--data-yaml",
            str(tmp_path / "data.yaml"),
            "--manifest-csv",
            str(tmp_path / "manifest.csv"),
            "--params-yaml",
            str(params_yaml),
        ],
    )

    with pytest.raises(
        ValueError,
        match=r"data\.sites must be a YAML list",
    ):
        module.main()


def test_merge_packed_site_datasets_cli_converts_site_values_to_strings(
    tmp_path: Path,
    monkeypatch,
):
    module = load_cli_module()

    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged_manifests"
    data_yaml = tmp_path / "data.yaml"
    params_yaml = tmp_path / "params.yaml"
    manifest_csv = tmp_path / "manifest.csv"

    # The CLI explicitly stringifies each item in data.sites.
    write_site_dataset(
        sites_root,
        "123",
        video_stem="ORG-site-device_20250101_000000_M",
    )

    write_text(data_yaml, "names:\n  0: Sockeye\n")
    write_text(
        params_yaml,
        yaml.safe_dump(
            {
                "data": {
                    "sites": [123],
                }
            },
            sort_keys=False,
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_packed_site_datasets.py",
            "--sites-root",
            str(sites_root),
            "--manifests-root",
            str(manifests_root),
            "--data-yaml",
            str(data_yaml),
            "--manifest-csv",
            str(manifest_csv),
            "--params-yaml",
            str(params_yaml),
        ],
    )

    module.main()

    assert (manifests_root / "active_sites.txt").read_text(
        encoding="utf-8"
    ) == "123\n"
