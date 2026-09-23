import csv
from pathlib import Path

import pytest
import yaml

from object_detection.dataset.merge import (
    _read_nonempty_lines,
    merge_packed_csvs,
    merge_site_manifests,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_site_manifests(
    sites_root: Path,
    site: str,
    *,
    train=(),
    val=(),
    test=(),
) -> None:
    manifests = sites_root / site / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)

    for split, lines in {
        "train": train,
        "val": val,
        "test": test,
    }.items():
        text = "\n".join(lines)
        if text:
            text += "\n"
        (manifests / f"{split}.txt").write_text(text, encoding="utf-8")


def write_packed_csv(
    sites_root: Path,
    site: str,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> Path:
    path = sites_root / site / "packed_dataset_manifest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return path


def test_read_nonempty_lines_strips_and_ignores_blanks(tmp_path: Path):
    path = tmp_path / "manifest.txt"
    write_text(
        path,
        "\n"
        " train/video_b/frame_000002.jpg \n"
        "\n"
        "train/video_a/frame_000001.jpg\n"
        "   \n",
    )

    assert _read_nonempty_lines(path) == [
        "train/video_b/frame_000002.jpg",
        "train/video_a/frame_000001.jpg",
    ]


def test_read_nonempty_lines_missing_file_returns_empty_list(tmp_path: Path):
    assert _read_nonempty_lines(tmp_path / "missing.txt") == []


def test_merge_site_manifests_merges_deduplicates_and_sorts(tmp_path: Path):
    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged" / "manifests"
    data_yaml = tmp_path / "salmon_yolo.yaml"

    write_site_manifests(
        sites_root,
        "bear",
        train=[
            "train/bear_video/frame_000020.jpg",
            "train/shared_video/frame_000001.jpg",
            "train/bear_video/frame_000010.jpg",
        ],
        val=["val/bear_video/frame_000030.jpg"],
        test=["test/bear_video/frame_000040.jpg"],
    )

    write_site_manifests(
        sites_root,
        "tankeeah",
        train=[
            "train/tankeeah_video/frame_000002.jpg",
            "train/shared_video/frame_000001.jpg",  # duplicate on purpose
        ],
        val=["val/tankeeah_video/frame_000003.jpg"],
        test=["test/tankeeah_video/frame_000004.jpg"],
    )

    names = {
        0: "Sockeye",
        1: "Coho",
    }
    write_text(
        data_yaml,
        yaml.safe_dump({"names": names}, sort_keys=False),
    )

    sites = ["bear", "tankeeah"]

    merge_site_manifests(
        sites_root=sites_root,
        sites=sites,
        manifests_root=manifests_root,
        data_yaml=data_yaml,
    )

    assert (manifests_root / "train.txt").read_text(encoding="utf-8") == (
        "train/bear_video/frame_000010.jpg\n"
        "train/bear_video/frame_000020.jpg\n"
        "train/shared_video/frame_000001.jpg\n"
        "train/tankeeah_video/frame_000002.jpg\n"
    )

    assert (manifests_root / "val.txt").read_text(encoding="utf-8") == (
        "val/bear_video/frame_000030.jpg\n"
        "val/tankeeah_video/frame_000003.jpg\n"
    )

    assert (manifests_root / "test.txt").read_text(encoding="utf-8") == (
        "test/bear_video/frame_000040.jpg\n"
        "test/tankeeah_video/frame_000004.jpg\n"
    )

    # The configured site order is preserved, rather than alphabetically sorted.
    assert (manifests_root / "active_sites.txt").read_text(encoding="utf-8") == (
        "bear\n"
        "tankeeah\n"
    )

    merged_yaml = yaml.safe_load(
        (manifests_root / "data.yaml").read_text(encoding="utf-8")
    )

    assert merged_yaml["train"] == str((manifests_root / "train.txt").resolve())
    assert merged_yaml["val"] == str((manifests_root / "val.txt").resolve())
    assert merged_yaml["test"] == str((manifests_root / "test.txt").resolve())
    assert merged_yaml["names"] == names


def test_merge_site_manifests_supports_empty_split_files(tmp_path: Path):
    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged"
    data_yaml = tmp_path / "data.yaml"

    write_site_manifests(
        sites_root,
        "tankeeah",
        train=["train/video/frame_000001.jpg"],
        val=[],
        test=[],
    )
    write_text(data_yaml, "names:\n  0: Sockeye\n")

    merge_site_manifests(
        sites_root=sites_root,
        sites=["tankeeah"],
        manifests_root=manifests_root,
        data_yaml=data_yaml,
    )

    assert (manifests_root / "train.txt").read_text(encoding="utf-8") == (
        "train/video/frame_000001.jpg\n"
    )
    assert (manifests_root / "val.txt").read_text(encoding="utf-8") == ""
    assert (manifests_root / "test.txt").read_text(encoding="utf-8") == ""


def test_merge_site_manifests_preserves_names_list(tmp_path: Path):
    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged"
    data_yaml = tmp_path / "data.yaml"

    write_site_manifests(sites_root, "tankeeah")
    write_text(
        data_yaml,
        yaml.safe_dump({"names": ["Sockeye", "Coho"]}, sort_keys=False),
    )

    merge_site_manifests(
        sites_root=sites_root,
        sites=["tankeeah"],
        manifests_root=manifests_root,
        data_yaml=data_yaml,
    )

    merged_yaml = yaml.safe_load(
        (manifests_root / "data.yaml").read_text(encoding="utf-8")
    )
    assert merged_yaml["names"] == ["Sockeye", "Coho"]


def test_merge_site_manifests_missing_site_manifest_raises(tmp_path: Path):
    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged"
    data_yaml = tmp_path / "data.yaml"

    write_site_manifests(sites_root, "tankeeah")

    # Bear has train/test but intentionally no val manifest.
    bear_manifests = sites_root / "bear" / "manifests"
    write_text(bear_manifests / "train.txt", "")
    write_text(bear_manifests / "test.txt", "")

    write_text(data_yaml, "names:\n  0: Sockeye\n")

    with pytest.raises(
        FileNotFoundError,
        match=r"Missing packed manifest for site 'bear'",
    ):
        merge_site_manifests(
            sites_root=sites_root,
            sites=["tankeeah", "bear"],
            manifests_root=manifests_root,
            data_yaml=data_yaml,
        )


def test_merge_site_manifests_missing_names_raises(tmp_path: Path):
    sites_root = tmp_path / "sites"
    manifests_root = tmp_path / "merged"
    data_yaml = tmp_path / "data.yaml"

    write_site_manifests(sites_root, "tankeeah")
    write_text(data_yaml, "train: something.txt\n")

    with pytest.raises(ValueError, match=r"No 'names' entry"):
        merge_site_manifests(
            sites_root=sites_root,
            sites=["tankeeah"],
            manifests_root=manifests_root,
            data_yaml=data_yaml,
        )


def test_merge_packed_csvs_merges_and_sorts_rows(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "merged" / "packed_dataset_manifest.csv"

    fieldnames = [
        "split",
        "video_stem",
        "requested_frames",
        "status",
    ]

    write_packed_csv(
        sites_root,
        "tankeeah",
        fieldnames,
        [
            {
                "split": "val",
                "video_stem": "tankeeah_b",
                "requested_frames": "2",
                "status": "ok",
            },
            {
                "split": "train",
                "video_stem": "tankeeah_a",
                "requested_frames": "3",
                "status": "ok",
            },
        ],
    )

    write_packed_csv(
        sites_root,
        "bear",
        fieldnames,
        [
            {
                "split": "train",
                "video_stem": "bear_b",
                "requested_frames": "4",
                "status": "ok",
            },
            {
                "split": "train",
                "video_stem": "bear_a",
                "requested_frames": "1",
                "status": "ok",
            },
        ],
    )

    merge_packed_csvs(
        sites_root=sites_root,
        sites=["tankeeah", "bear"],
        out_csv=out_csv,
    )

    with out_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert reader.fieldnames == fieldnames
    assert [
        (row["split"], row["video_stem"])
        for row in rows
    ] == [
        ("train", "bear_a"),
        ("train", "bear_b"),
        ("train", "tankeeah_a"),
        ("val", "tankeeah_b"),
    ]

    # Parent output directory should have been created automatically.
    assert out_csv.exists()


def test_merge_packed_csvs_accepts_header_only_site_csv(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    fieldnames = ["split", "video_stem", "status"]

    write_packed_csv(
        sites_root,
        "empty_site",
        fieldnames,
        [],
    )
    write_packed_csv(
        sites_root,
        "tankeeah",
        fieldnames,
        [
            {
                "split": "train",
                "video_stem": "video_a",
                "status": "ok",
            }
        ],
    )

    merge_packed_csvs(
        sites_root=sites_root,
        sites=["empty_site", "tankeeah"],
        out_csv=out_csv,
    )

    with out_csv.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["video_stem"] == "video_a"


def test_merge_packed_csvs_all_header_only_writes_header_only(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    fieldnames = ["split", "video_stem", "status"]

    write_packed_csv(sites_root, "tankeeah", fieldnames, [])
    write_packed_csv(sites_root, "bear", fieldnames, [])

    merge_packed_csvs(
        sites_root=sites_root,
        sites=["tankeeah", "bear"],
        out_csv=out_csv,
    )

    assert out_csv.read_text(encoding="utf-8") == (
        "split,video_stem,status\n"
    )


def test_merge_packed_csvs_missing_site_csv_raises(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    fieldnames = ["split", "video_stem"]

    write_packed_csv(
        sites_root,
        "tankeeah",
        fieldnames,
        [{"split": "train", "video_stem": "video_a"}],
    )

    with pytest.raises(
        FileNotFoundError,
        match=r"Missing packed dataset CSV for site 'bear'",
    ):
        merge_packed_csvs(
            sites_root=sites_root,
            sites=["tankeeah", "bear"],
            out_csv=out_csv,
        )


def test_merge_packed_csvs_mismatched_columns_raises(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    write_packed_csv(
        sites_root,
        "tankeeah",
        ["split", "video_stem", "status"],
        [{"split": "train", "video_stem": "a", "status": "ok"}],
    )
    write_packed_csv(
        sites_root,
        "bear",
        ["split", "video_stem", "images_written"],
        [{"split": "train", "video_stem": "b", "images_written": "1"}],
    )

    with pytest.raises(ValueError, match=r"CSV columns differ"):
        merge_packed_csvs(
            sites_root=sites_root,
            sites=["tankeeah", "bear"],
            out_csv=out_csv,
        )


def test_merge_packed_csvs_same_columns_different_order_raises(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    write_packed_csv(
        sites_root,
        "tankeeah",
        ["split", "video_stem", "status"],
        [{"split": "train", "video_stem": "a", "status": "ok"}],
    )
    write_packed_csv(
        sites_root,
        "bear",
        ["video_stem", "split", "status"],
        [{"split": "train", "video_stem": "b", "status": "ok"}],
    )

    with pytest.raises(ValueError, match=r"CSV columns differ"):
        merge_packed_csvs(
            sites_root=sites_root,
            sites=["tankeeah", "bear"],
            out_csv=out_csv,
        )


def test_merge_packed_csvs_empty_files_raise(tmp_path: Path):
    sites_root = tmp_path / "sites"
    out_csv = tmp_path / "out.csv"

    for site in ("tankeeah", "bear"):
        path = sites_root / site / "packed_dataset_manifest.csv"
        write_text(path, "")

    with pytest.raises(
        RuntimeError,
        match=r"No packed dataset CSV rows found",
    ):
        merge_packed_csvs(
            sites_root=sites_root,
            sites=["tankeeah", "bear"],
            out_csv=out_csv,
        )


def test_merge_packed_csvs_empty_site_list_raises(tmp_path: Path):
    with pytest.raises(
        RuntimeError,
        match=r"No packed dataset CSV rows found",
    ):
        merge_packed_csvs(
            sites_root=tmp_path / "sites",
            sites=[],
            out_csv=tmp_path / "out.csv",
        )
