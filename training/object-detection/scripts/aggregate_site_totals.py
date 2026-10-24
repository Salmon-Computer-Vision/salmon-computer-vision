#!/usr/bin/env python3
"""Combine per-site yolo_ls site_totals.csv files for active params.data.sites.

Keeps the converter's definitions (videos WITH boxes, sampled positive frames,
boxes, and selected negative frames), and recalculates percentage fields across
active sites.  Does not scan raw JSON or massive annotation shards.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

COUNT_COLS = (
    'total_frames_with_boxes',
    'total_boxes',
    'total_videos_with_boxes',
    'negative_from_empty',
    'negative_from_annotated',
    'negative_total',
    'total_frames_including_negatives',
)
OUTPUT_COLS = (
    'site',
    *COUNT_COLS,
    'negative_fraction',
    'frame_pct_of_dataset',
    'box_pct_of_dataset',
    'frames_per_video_with_boxes',
    'boxes_per_video_with_boxes',
    'boxes_per_positive_frame',
    'row_type',
)


def _positive_int(value: str, path: Path, key: str) -> int:
    try:
        value = str(value).strip()
        if not value or not value.isdecimal():
            raise ValueError
        return int(value)
    except ValueError as exc:
        raise ValueError(f'{path}: {key} must be a non-negative integer; got {value!r}') from exc


def load_sites(params_path: Path) -> list[str]:
    obj = yaml.safe_load(params_path.read_text(encoding='utf-8'))
    sites = (obj or {}).get('data', {}).get('sites')
    if not isinstance(sites, list) or not sites:
        raise ValueError(f'{params_path}: data.sites must be a nonempty YAML list')
    if not all(isinstance(s, str) and s.strip() and s == s.strip() for s in sites):
        raise ValueError('data.sites entries must be nonempty site names')
    if len(set(sites)) != len(sites):
        raise ValueError('data.sites contains duplicate site names')
    return sites


def _read_site(site: str, sites_root: Path) -> dict[str, int | str]:
    path = sites_root / site / 'yolo_annos_stats' / 'site_totals.csv'
    if not path.is_file():
        raise FileNotFoundError(f'Missing site totals for {site!r}: {path}')
    with path.open(newline='', encoding='utf-8-sig') as fp:
        reader = csv.DictReader(fp)
        required = {'site', *COUNT_COLS}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path}: missing CSV columns {sorted(missing)}')
        rows = list(reader)
    # The converter can emit a header-only CSV if a reviewed site has no
    # positive fish annotations. Preserve it as an all-zero entry.
    if not rows:
        return {'site': site, **{col: 0 for col in COUNT_COLS}}
    if len(rows) != 1 or rows[0]['site'] != site:
        raise ValueError(f'{path}: expected exactly one row for site {site!r}; found {[r.get("site") for r in rows]}')
    row = {'site': site}
    for col in COUNT_COLS:
        row[col] = _positive_int(rows[0][col], path, col)
    if row['negative_from_empty'] + row['negative_from_annotated'] != row['negative_total']:
        raise ValueError(f'{path}: negative_total does not equal the two negative sources')
    if row['total_frames_with_boxes'] + row['negative_total'] != row['total_frames_including_negatives']:
        raise ValueError(f'{path}: total_frames_including_negatives is inconsistent')
    return row


def _enrich(row: dict, total_positive: int, total_boxes: int, row_type: str) -> dict:
    row = dict(row)
    positive = row['total_frames_with_boxes']
    boxes = row['total_boxes']
    videos = row['total_videos_with_boxes']
    negative = row['negative_total']
    all_frames = positive + negative
    row.update({
        'negative_fraction': round(negative / all_frames, 6) if all_frames else 0.0,
        'frame_pct_of_dataset': round(100 * positive / total_positive, 6) if total_positive else 0.0,
        'box_pct_of_dataset': round(100 * boxes / total_boxes, 6) if total_boxes else 0.0,
        'frames_per_video_with_boxes': round(positive / videos, 3) if videos else 0.0,
        'boxes_per_video_with_boxes': round(boxes / videos, 3) if videos else 0.0,
        'boxes_per_positive_frame': round(boxes / positive, 3) if positive else 0.0,
        'row_type': row_type,
    })
    return row


def aggregate_site_totals(params_yaml: Path, sites_root: Path, out_csv: Path) -> list[dict]:
    sites = load_sites(params_yaml)
    rows = [_read_site(site, sites_root) for site in sites]
    totals = {'site': 'ALL_SITES'}
    totals.update({col: sum(row[col] for row in rows) for col in COUNT_COLS})
    all_positive = totals['total_frames_with_boxes']
    all_boxes = totals['total_boxes']
    result = [_enrich(row, all_positive, all_boxes, 'site') for row in rows]
    result.append(_enrich(totals, all_positive, all_boxes, 'total'))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', newline='', encoding='utf-8') as fp:
        writer = csv.DictWriter(fp, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params-yaml', type=Path, default=Path('params.yaml'))
    parser.add_argument('--sites-root', type=Path, default=Path('data/02_interim/annotation_stats_by_site'))
    parser.add_argument('--out-csv', type=Path, default=Path('data/03_processed/annotation_stats/site_totals.csv'))
    args = parser.parse_args()
    rows = aggregate_site_totals(args.params_yaml, args.sites_root, args.out_csv)
    totals = rows[-1]
    print(f'Aggregated {len(rows)-1} active site(s) -> {args.out_csv}: '
          f'{totals["total_videos_with_boxes"]} fish-positive videos, '
          f'{totals["total_frames_with_boxes"]} positive frames, '
          f'{totals["total_boxes"]} boxes, '
          f'{totals["negative_total"]} selected negative frames')


if __name__ == '__main__':
    main()
