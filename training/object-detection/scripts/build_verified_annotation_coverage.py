#!/usr/bin/env python3
"""Declare review coverage for human-reviewed Label Studio source sequences.

Policy: site Label Studio tasks have been reviewed to completion. No-track tasks
count as verified negatives unless zero GT results solely from dropped malformed
tracks. Non-Label-Studio sources require separate review/provenance.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

DROP_COUNTERS = (
    "degenerate_tracks_dropped",
    "out_of_range_tracks_dropped",
    "fully_outside_tracks_dropped",
)


def _nonnegative_int(value: str, column: str, stem: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{stem}: invalid {column}={value!r}") from exc
    if n < 0:
        raise ValueError(f"{stem}: negative {column}={n}")
    return n


def build_coverage(input_csv: Path, output_csv: Path, *, split: str) -> dict[str, int]:
    if split not in {"val", "test"}:
        raise ValueError(f"Unsupported split {split!r}")
    with input_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"split", "video_stem", "status", "source_json", "n_gt_rows"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{input_csv}: missing columns {sorted(missing)}")
        source = list(reader)

    rows = []
    seen = set()
    counters = {"total": 0, "verified_with_gt": 0, "verified_empty_gt": 0,
                "unverified": 0, "flagged_sanitized_empty": 0}
    for row in source:
        stem = (row.get("video_stem") or "").strip()
        if not stem or stem in seen:
            raise ValueError(f"Duplicate or missing video_stem: {stem!r}")
        seen.add(stem)
        if row.get("split") != split:
            raise ValueError(f"Split mismatch for {stem}: {row.get('split')!r} != {split!r}")
        status = (row.get("status") or "").strip()
        n_gt = _nonnegative_int(row.get("n_gt_rows", ""), "n_gt_rows", stem)
        dropped_tracks = sum(_nonnegative_int(row.get(col) or "0", col, stem)
                             for col in DROP_COUNTERS)
        source_json_present = bool((row.get("source_json") or "").strip())

        if status == "ok" and n_gt == 0:
            raise ValueError(f"{stem}: status=ok but n_gt_rows=0")
        if status == "no_tracks" and n_gt != 0:
            raise ValueError(f"{stem}: status=no_tracks but n_gt_rows={n_gt}")

        reviewed = status in {"ok", "no_tracks"} and source_json_present
        reason = "human_reviewed_labelstudio_task" if reviewed else "not_labelstudio_reviewed"
        if reviewed and n_gt == 0 and dropped_tracks > 0:
            reviewed = False
            reason = "empty_gt_after_dropped_tracks_requires_review"
            counters["flagged_sanitized_empty"] += 1
        if not reviewed:
            counters["unverified"] += 1
        elif n_gt == 0:
            counters["verified_empty_gt"] += 1
        else:
            counters["verified_with_gt"] += 1
        counters["total"] += 1
        rows.append({
            "video_stem": stem,
            "fully_annotated": "true" if reviewed else "false",
            "review_basis": reason,
            "source_status": status,
            "n_gt_rows": str(n_gt),
        })

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_csv.with_name(output_csv.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else
                                    ["video_stem", "fully_annotated", "review_basis", "source_status", "n_gt_rows"])
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda r: r["video_stem"]))
        tmp.replace(output_csv)
    finally:
        tmp.unlink(missing_ok=True)
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences-csv", required=True, type=Path)
    parser.add_argument("--out-csv", required=True, type=Path)
    parser.add_argument("--split", choices=("val", "test"), required=True)
    args = parser.parse_args()
    counts = build_coverage(args.sequences_csv, args.out_csv, split=args.split)
    print("Annotation review coverage: " + " ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
