from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Sequence

import yaml


def _read_nonempty_lines(path: Path) -> List[str]:
    if not path.exists():
        return []

    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def merge_site_manifests(
    *,
    sites_root: Path,
    sites: Sequence[str],
    manifests_root: Path,
    data_yaml: Path,
    splits: Iterable[str] = ("train", "val", "test"),
) -> None:
    manifests_root.mkdir(parents=True, exist_ok=True)

    for split in splits:
        lines = []

        for site in sites:
            src = sites_root / site / "manifests" / f"{split}.txt"

            if not src.exists():
                raise FileNotFoundError(
                    f"Missing packed manifest for site {site!r}: {src}"
                )

            lines.extend(_read_nonempty_lines(src))

        # Deduplicate defensively, while remaining deterministic.
        lines = sorted(set(lines))

        dst = manifests_root / f"{split}.txt"
        dst.write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )

    source_yaml = yaml.safe_load(
        Path(data_yaml).read_text(encoding="utf-8")
    )

    names = source_yaml.get("names")
    if names is None:
        raise ValueError(f"No 'names' entry in {data_yaml}")

    merged_yaml = {
        "train": str((manifests_root / "train.txt").resolve()),
        "val": str((manifests_root / "val.txt").resolve()),
        "test": str((manifests_root / "test.txt").resolve()),
        "names": names,
    }

    (manifests_root / "data.yaml").write_text(
        yaml.safe_dump(
            merged_yaml,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    (manifests_root / "active_sites.txt").write_text(
        "\n".join(sites) + "\n",
        encoding="utf-8",
    )


def merge_packed_csvs(
    *,
    sites_root: Path,
    sites: Sequence[str],
    out_csv: Path,
) -> None:
    rows = []
    fieldnames = None

    for site in sites:
        src = sites_root / site / "packed_dataset_manifest.csv"

        if not src.exists():
            raise FileNotFoundError(
                f"Missing packed dataset CSV for site {site!r}: {src}"
            )

        with src.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                continue

            if fieldnames is None:
                fieldnames = list(reader.fieldnames)
            elif list(reader.fieldnames) != fieldnames:
                raise ValueError(
                    f"CSV columns differ in {src}: "
                    f"{reader.fieldnames} != {fieldnames}"
                )

            rows.extend(reader)

    if fieldnames is None:
        raise RuntimeError("No packed dataset CSV rows found")

    rows.sort(
        key=lambda r: (
            r.get("split", ""),
            r.get("video_stem", ""),
        )
    )

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
