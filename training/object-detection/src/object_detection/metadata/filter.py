from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Optional


SITE_COLUMNS = (
    "site",
    "site_name",
    "metadata_file_site_reference_string",
)


def infer_site(row: Dict[str, str]) -> Optional[str]:
    # Prefer an explicit site column if the metadata index contains one.
    for column in SITE_COLUMNS:
        value = (row.get(column) or "").strip()
        if value:
            return value

    # Your normal S3 layout is:
    #
    #   ORG/site/device/motion_vids/video.mp4
    #
    # so site is path component 1.
    s3_key = (row.get("s3_key") or "").strip()

    if s3_key.startswith("s3://"):
        # s3://bucket/ORG/site/device/...
        remainder = s3_key[5:]
        parts = remainder.split("/")
        if len(parts) >= 3:
            return parts[2]
    else:
        # ORG/site/device/...
        parts = s3_key.lstrip("/").split("/")
        if len(parts) >= 2:
            return parts[1]

    return None


def filter_metadata_csv_by_site(
    *,
    input_csv: Path,
    site: str,
    out_csv: Path,
) -> int:
    input_csv = Path(input_csv)
    out_csv = Path(out_csv)

    wanted = site.casefold()

    with input_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"No CSV header in {input_csv}")

        fieldnames = list(reader.fieldnames)

        rows = []

        for row in reader:
            row_site = infer_site(row)

            if row_site is None:
                continue

            if row_site.casefold() == wanted:
                rows.append(row)

    if not rows:
        raise RuntimeError(
            f"No metadata rows found for site {site!r} in {input_csv}"
        )

    rows.sort(
        key=lambda row: (
            row.get("video_stem") or "",
            row.get("s3_key") or "",
        )
    )

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
