from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aggregate_site_totals', ROOT / 'scripts/aggregate_site_totals.py')
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def write_params(tmp_path, sites):
    path = tmp_path / 'params.yaml'
    path.write_text(yaml.safe_dump({'data': {'sites': sites}}))
    return path


def write_site(root, site, *, frames=0, boxes=0, videos=0, neg_empty=0, neg_annotated=0, header_only=False):
    path = root / site / 'yolo_annos_stats' / 'site_totals.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=['site', *mod.COUNT_COLS, 'negative_fraction'])
        writer.writeheader()
        if not header_only:
            writer.writerow({'site': site, 'total_frames_with_boxes': frames,
                'total_boxes': boxes, 'total_videos_with_boxes': videos,
                'negative_from_empty': neg_empty, 'negative_from_annotated': neg_annotated,
                'negative_total': neg_empty + neg_annotated,
                'total_frames_including_negatives': frames + neg_empty + neg_annotated,
                'negative_fraction': 0})
    return path


def test_counts_totals_ratios_and_site_order(tmp_path):
    root = tmp_path / 'collected'
    write_site(root, 'siteB', frames=8, boxes=12, videos=2, neg_empty=3)
    write_site(root, 'siteA', frames=12, boxes=36, videos=3, neg_annotated=2)
    params = write_params(tmp_path, ['siteA', 'siteB'])
    out = tmp_path / 'output.csv'
    rows = mod.aggregate_site_totals(params, root, out)
    assert [r['site'] for r in rows] == ['siteA', 'siteB', 'ALL_SITES']
    assert rows[0]['frame_pct_of_dataset'] == 60
    assert rows[1]['frame_pct_of_dataset'] == 40
    assert rows[0]['box_pct_of_dataset'] == 75
    assert rows[0]['frames_per_video_with_boxes'] == 4
    assert rows[0]['boxes_per_positive_frame'] == 3
    assert rows[0]['negative_fraction'] == round(2 / 14, 6)
    total = rows[-1]
    assert total['total_videos_with_boxes'] == 5
    assert total['total_frames_with_boxes'] == 20
    assert total['total_boxes'] == 48
    assert total['negative_total'] == 5
    assert total['total_frames_including_negatives'] == 25
    assert total['box_pct_of_dataset'] == 100
    assert total['row_type'] == 'total'
    with out.open(newline='') as f:
        data = list(csv.DictReader(f))
    assert len(data) == 3
    assert data[-1]['site'] == 'ALL_SITES'


def test_any_site_set_add_remove_and_nonhardcoded(tmp_path):
    root = tmp_path / 'collected'
    write_site(root, 'future_station', frames=5, boxes=7, videos=1)
    write_site(root, 'AnotherSite', frames=15, boxes=20, videos=4)
    params = write_params(tmp_path, ['future_station'])
    out = tmp_path / 'site_totals.csv'
    assert len(mod.aggregate_site_totals(params, root, out)) == 2
    params = write_params(tmp_path, ['AnotherSite', 'future_station'])
    assert len(mod.aggregate_site_totals(params, root, out)) == 3
    params = write_params(tmp_path, ['AnotherSite'])
    result = mod.aggregate_site_totals(params, root, out)
    assert [r['site'] for r in result] == ['AnotherSite', 'ALL_SITES']
    assert result[-1]['total_boxes'] == 20


def test_empty_site_header_only_is_zero_not_skipped(tmp_path):
    root = tmp_path / 'collected'
    write_site(root, 'empty', header_only=True)
    rows = mod.aggregate_site_totals(write_params(tmp_path, ['empty']), root, tmp_path / 'out.csv')
    assert len(rows) == 2
    assert rows[0]['total_frames_with_boxes'] == 0
    assert rows[0]['total_videos_with_boxes'] == 0
    assert rows[-1]['boxes_per_positive_frame'] == 0


def test_missing_site_input_fails_explicitly(tmp_path):
    params = write_params(tmp_path, ['site_without_file'])
    with pytest.raises(FileNotFoundError, match='site_without_file'):
        mod.aggregate_site_totals(params, tmp_path, tmp_path / 'out.csv')


def test_bad_site_row_does_not_silently_merge(tmp_path):
    root = tmp_path / 'collected'
    path = write_site(root, 'one', frames=5, boxes=5, videos=1)
    text = path.read_text().replace('\none,', '\nother,')
    path.write_text(text)
    with pytest.raises(ValueError, match='expected exactly one row'):
        mod.aggregate_site_totals(write_params(tmp_path, ['one']), root, tmp_path / 'out.csv')


def test_duplicates_in_site_selection_rejected(tmp_path):
    with pytest.raises(ValueError, match='duplicate'):
        mod.load_sites(write_params(tmp_path, ['one', 'one']))


def test_negative_breakdown_validation(tmp_path):
    root = tmp_path / 'collected'
    path = write_site(root, 'one', frames=5, boxes=5, videos=1, neg_empty=2)
    text = path.read_text().replace('one,5,5,1,2,0,2,7,0', 'one,5,5,1,2,0,3,7,0')
    path.write_text(text)
    with pytest.raises(ValueError, match='negative_total'):
        mod.aggregate_site_totals(write_params(tmp_path, ['one']), root, tmp_path / 'out.csv')


def test_dvc_stage_and_named_plots_are_valid():
    dvc = yaml.safe_load((ROOT / 'dvc.yaml').read_text())
    stages = dvc['stages']
    assert 'aggregate_site_totals' in stages
    assert 'data.sites' in stages['aggregate_site_totals']['params']
    collect = stages['collect_site_class_stats']['do']
    assert 'site_totals.csv' in collect['cmd']
    assert any(str(dep).endswith('site_totals.csv') for dep in collect['deps'])
    assert 'data/02_interim/annotation_stats_by_site' in stages['aggregate_site_totals']['deps']
    assert 'data/03_processed/annotation_stats/site_totals.csv' in stages['aggregate_site_totals']['outs']
    names = {next(iter(p)) for p in dvc['plots']}
    assert {'annotation_site_videos', 'annotation_site_frames', 'annotation_site_boxes'} <= names
    template = json.loads((ROOT / 'config/plots/site_totals_bars.vl.json').read_text())
    assert template['data']['values'] == '<DVC_METRIC_DATA>'
    assert any('ALL_SITES' in str(t) for t in template['transform'])
