from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from object_detection.splits.splitter import (
    build_groups,
    enforce_minimum_video_splits,
    split_groups_greedy,
)

WEIGHTS = {"class": 4.0, "tod": 1.0, "density": 1.0,
           "area": 1.0, "ar": 1.0, "size": 2.0}


def make_frames(root: Path, specs):
    """specs = (device, date, video_idx, n_frames)."""
    for device, date, idx, n_frames in specs:
        stem = f"GWA-fcn-{device}_{date}_{idx:06d}_M"
        d = root / stem
        d.mkdir(parents=True)
        for j in range(n_frames):
            (d / f"frame_{j:06d}.txt").write_text(
                "0 0.5 0.5 0.2 0.1\n" if j % 3 else ""
            )


def get_split(root, **settings):
    groups = build_groups(root, ["fcn"], seed=42)
    base = split_groups_greedy(groups, 42, .8, .1, .1, WEIGHTS)
    result = enforce_minimum_video_splits(
        groups, *base[:3], seed=42, train_frac=.8, val_frac=.1,
        test_frac=.1, **settings,
    )
    return groups, result


def assert_invariants(groups, result):
    train, val, test, assign, meta = result
    all_frames = set()
    all_videos = set()
    for g in groups.values():
        all_frames.update(g.frame_paths)
        all_videos.update(g.video_stats)
    assert set(assign) == all_videos
    assert len(assign) == len(all_videos)
    subsets = [set(s.frame_paths) for s in (train, val, test)]
    assert subsets[0].isdisjoint(subsets[1])
    assert subsets[0].isdisjoint(subsets[2])
    assert subsets[1].isdisjoint(subsets[2])
    assert set.union(*subsets) == all_frames
    for name in ("train", "val", "test"):
        assert meta['actual_videos'][name] >= meta['effective_min_videos'][name]
    for frames in subsets:
        for stem in set(Path(f).parent.name for f in frames):
            assert all(Path(f).parent.name != stem for other in subsets if other is not frames for f in other)


def test_sparse_two_day_groups_get_video_blocks(tmp_path):
    specs = [(f"camera-{cam}", "20250720", i, 9)
             for cam in (1, 2) for i in range(100000, 100012)]
    make_frames(tmp_path, specs)
    groups, result = get_split(tmp_path, min_val_videos=2, min_test_videos=2)
    assert len(groups) == 2
    assert result[4]['strategy'] == 'temporal_video_blocks'
    assert result[4]['n_groups_shared_across_splits'] >= 1
    assert abs(result[0].n_frames - 0.8 * 24 * 9) < 30
    assert_invariants(groups, result)


def test_sparse_all_on_one_day(tmp_path):
    make_frames(tmp_path, [("camera-1", "20250720", i, 5)
                           for i in range(100000, 100008)])
    groups, result = get_split(tmp_path, min_val_videos=2, min_test_videos=2)
    assert len(groups) == 1
    assert result[4]['strategy'] == 'temporal_video_blocks'
    assert_invariants(groups, result)


def test_group_only_repair_preserves_isolation(tmp_path):
    # 5 device-days, each with one 100-frame video. Moving groups is sufficient.
    make_frames(tmp_path, [(f"camera-{i}", "20250720", 100000, 80)
                           for i in range(5)])
    groups, result = get_split(tmp_path, min_val_videos=1, min_test_videos=1)
    assert result[4]['strategy'] in ('day_groups', 'repaired_day_groups')
    assert result[4]['n_groups_shared_across_splits'] == 0
    assert_invariants(groups, result)


def test_reduces_minimum_when_four_videos(tmp_path):
    make_frames(tmp_path, [("camera-1", "20250720", i, 3)
                           for i in range(100000, 100004)])
    groups, result = get_split(tmp_path, min_val_videos=2, min_test_videos=2)
    assert result[4]['minimums_reduced'] is True
    assert result[4]['effective_min_videos'] == {"train": 1, "val": 1, "test": 1}
    assert_invariants(groups, result)


def test_two_videos_fails_instead_of_silent_empty_splits(tmp_path):
    make_frames(tmp_path, [("camera-1", "20250720", i, 3)
                           for i in range(100000, 100002)])
    with pytest.raises(ValueError, match="at least 3"):
        get_split(tmp_path)


def test_deterministic(tmp_path):
    make_frames(tmp_path, [(f"camera-{cam}", "20250720", i, 7)
                           for cam in (1, 2) for i in range(100000, 100011)])
    a = get_split(tmp_path)[1]
    b = get_split(tmp_path)[1]
    assert a[3] == b[3]
    assert a[4] == b[4]


def test_end_to_end_cli_and_group_csv(tmp_path):
    root = tmp_path / "labels"
    make_frames(root, [(f"camera-{cam}", "20250720", i, 6)
                       for cam in (1,2) for i in range(100000, 100009)])
    out = tmp_path / "splits"
    env = dict(os.environ)
    # use bundled drop-in code in preference to anything preinstalled
    repo = Path(__file__).resolve().parents[1]
    env['PYTHONPATH'] = str(repo / 'src')
    result = subprocess.run([
        sys.executable, str(repo / 'scripts/make_splits.py'),
        '--labels-root', str(root), '--out-dir', str(out),
        '--sites', 'fcn', '--min-val-videos', '2', '--min-test-videos', '2',
    ], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((out / 'split_report.json').read_text())
    assert data['video_coverage']['actual_videos']['val'] >= 2
    assert data['video_coverage']['actual_videos']['test'] >= 2
    manifest_frames = [line for name in ('train','val','test')
                       for line in (out / f'{name}.txt').read_text().splitlines()]
    assert len(manifest_frames) == len(set(manifest_frames)) == 18 * 6
    video_rows = list(csv.DictReader((out / 'video_assignments.csv').open()))
    group_rows = list(csv.DictReader((out / 'group_assignments.csv').open()))
    assert len(video_rows) == 18
    assert sum(int(row['n_frames']) for row in group_rows) == 18 * 6
    assert sum(int(row['n_videos']) for row in group_rows) == 18
    assert sum(data['targets']['actual_frames'].values()) == 18 * 6


def test_dvc_declares_parameters():
    repo = Path(__file__).resolve().parents[1]
    dvc = yaml.safe_load((repo / 'dvc.yaml').read_text())
    params = yaml.safe_load((repo / 'params.yaml').read_text())
    stage = dvc['stages']['split_data']['do']
    assert '${split.min_val_videos}' in stage['cmd']
    assert '${split.min_test_videos}' in stage['cmd']
    assert set(stage['params']) == {'split.min_val_videos', 'split.min_test_videos'}
    assert params['split'] == {'min_val_videos': 2, 'min_test_videos': 2}
