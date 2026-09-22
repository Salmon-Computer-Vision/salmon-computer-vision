import json
from pathlib import Path

import pytest

from object_detection.metadata.site_index import (
    build_site_index,
    inspect_export,
    iter_tasks,
    safe_site_filename,
    sha256_file,
)


def task(site=None, *, org=None, camera=None, task_id=None):
    data = {}
    if site is not None:
        data['metadata_file_site_reference_string'] = site
    if org is not None:
        data['metadata_file_organization_reference_string'] = org
    if camera is not None:
        data['metadata_file_camera_reference_string'] = camera

    result = {'data': data}
    if task_id is not None:
        result['id'] = task_id
    return result


def write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_iter_tasks_supports_list_single_task_and_tasks_wrapper():
    t1 = task('tankeeah', task_id=1)
    t2 = task('bear', task_id=2)

    assert list(iter_tasks([t1, 'ignore', t2])) == [t1, t2]
    assert list(iter_tasks(t1)) == [t1]
    assert list(iter_tasks({'tasks': [t1, None, t2]})) == [t1, t2]
    assert list(iter_tasks({'not_tasks': []})) == []


def test_sha256_file_is_content_based(tmp_path: Path):
    a = tmp_path / 'a.json'
    b = tmp_path / 'b.json'
    a.write_bytes(b'same bytes')
    b.write_bytes(b'same bytes')

    assert sha256_file(a) == sha256_file(b)


def test_inspect_export_mixed_sites_counts_missing_and_collects_metadata(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    export = write_json(
        raw_root / 'nested' / 'mixed.json',
        [
            task('tankeeah', org='HIRMD', camera='jetson-1', task_id=1),
            task('tankeeah', org='HIRMD', camera='jetson-0', task_id=2),
            task('tankeeah', org='HIRMD', camera='jetson-1', task_id=3),
            task('chignik', org='ADFG', camera='jetsonorin-0', task_id=4),
            task(None, org='UNKNOWN', camera='x', task_id=5),
        ],
    )

    records, missing = inspect_export(export, raw_root=raw_root)

    assert missing == 1
    assert set(records) == {'tankeeah', 'chignik'}

    tankeeah = records['tankeeah']
    assert tankeeah.path == 'nested/mixed.json'
    assert tankeeah.sha256 == sha256_file(export)
    assert tankeeah.task_count == 3
    assert tankeeah.total_tasks == 5
    assert tankeeah.organizations == ['HIRMD']
    assert tankeeah.cameras == ['jetson-0', 'jetson-1']

    chignik = records['chignik']
    assert chignik.task_count == 1
    assert chignik.total_tasks == 5
    assert chignik.organizations == ['ADFG']
    assert chignik.cameras == ['jetsonorin-0']


def test_inspect_export_with_no_site_metadata_returns_no_records(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    export = write_json(
        raw_root / 'missing.json',
        [task(None), task('   ')],
    )

    records, missing = inspect_export(export, raw_root=raw_root)
    assert records == {}
    assert missing == 2


@pytest.mark.parametrize(
    ('site', 'expected'),
    [
        ('tankeeah', 'tankeeah'),
        ('Elbow', 'Elbow'),
        ('Chignik 2024 / J-0', 'Chignik_2024_J-0'),
        (' site:name ', 'site_name'),
    ],
)
def test_safe_site_filename(site: str, expected: str):
    assert safe_site_filename(site) == expected


def test_safe_site_filename_rejects_empty_site():
    with pytest.raises(ValueError, match='Empty site name'):
        safe_site_filename('   ')


def test_build_site_index_writes_site_manifests_summary_and_mixed_file_membership(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    out_dir = tmp_path / 'index'

    write_json(
        raw_root / 'a.json',
        [
            task('tankeeah', org='HIRMD', camera='jetson-1'),
            task('tankeeah', org='HIRMD', camera='jetson-0'),
        ],
    )
    write_json(
        raw_root / 'nested' / 'mixed.json',
        [
            task('tankeeah', org='HIRMD', camera='jetson-0'),
            task('chignik', org='ADFG', camera='jetsonorin-0'),
            task(None),
        ],
    )
    write_json(raw_root / 'no-site.json', [task(None)])

    summary = build_site_index(raw_root=raw_root, out_dir=out_dir)

    assert summary['json_files_seen'] == 3
    assert summary['site_count'] == 2
    assert summary['tasks_missing_site'] == 2
    assert summary['files_without_site'] == 1
    assert set(summary['sites']) == {'tankeeah', 'chignik'}

    tankeeah_manifest = json.loads((out_dir / 'tankeeah.json').read_text(encoding='utf-8'))
    chignik_manifest = json.loads((out_dir / 'chignik.json').read_text(encoding='utf-8'))
    saved_summary = json.loads((out_dir / 'summary.json').read_text(encoding='utf-8'))

    assert tankeeah_manifest['site'] == 'tankeeah'
    assert tankeeah_manifest['file_count'] == 2
    assert tankeeah_manifest['task_count'] == 3
    assert [f['path'] for f in tankeeah_manifest['files']] == [
        'a.json',
        'nested/mixed.json',
    ]

    assert chignik_manifest['file_count'] == 1
    assert chignik_manifest['task_count'] == 1
    assert chignik_manifest['files'][0]['path'] == 'nested/mixed.json'

    # The same mixed source export must be referenced by both site manifests.
    tankeeah_mixed = next(f for f in tankeeah_manifest['files'] if f['path'] == 'nested/mixed.json')
    chignik_mixed = chignik_manifest['files'][0]
    assert tankeeah_mixed['sha256'] == chignik_mixed['sha256']
    assert tankeeah_mixed['total_tasks'] == 3
    assert chignik_mixed['total_tasks'] == 3
    assert tankeeah_mixed['task_count'] == 1
    assert chignik_mixed['task_count'] == 1

    assert saved_summary == summary


def test_build_site_index_is_deterministic_across_rebuilds(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    out_dir = tmp_path / 'index'

    write_json(
        raw_root / 'z.json',
        [task('tankeeah', org='HIRMD', camera='jetson-1')],
    )
    write_json(
        raw_root / 'a.json',
        [task('tankeeah', org='HIRMD', camera='jetson-0')],
    )

    build_site_index(raw_root=raw_root, out_dir=out_dir)
    first_manifest = (out_dir / 'tankeeah.json').read_bytes()
    first_summary = (out_dir / 'summary.json').read_bytes()

    build_site_index(raw_root=raw_root, out_dir=out_dir)

    assert (out_dir / 'tankeeah.json').read_bytes() == first_manifest
    assert (out_dir / 'summary.json').read_bytes() == first_summary


def test_build_site_index_removes_stale_manifests(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    out_dir = tmp_path / 'index'
    out_dir.mkdir(parents=True)

    (out_dir / 'oldsite.json').write_text('{"stale": true}\n', encoding='utf-8')
    write_json(raw_root / 'current.json', [task('tankeeah')])

    build_site_index(raw_root=raw_root, out_dir=out_dir)

    assert not (out_dir / 'oldsite.json').exists()
    assert (out_dir / 'tankeeah.json').exists()
    assert (out_dir / 'summary.json').exists()


def test_build_site_index_allowed_sites_only_writes_requested_sites(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    out_dir = tmp_path / 'index'

    write_json(
        raw_root / 'mixed.json',
        [task('tankeeah'), task('chignik'), task('bear')],
    )

    summary = build_site_index(
        raw_root=raw_root,
        out_dir=out_dir,
        allowed_sites={'chignik'},
    )

    assert summary['site_count'] == 1
    assert set(summary['sites']) == {'chignik'}
    assert (out_dir / 'chignik.json').exists()
    assert not (out_dir / 'tankeeah.json').exists()
    assert not (out_dir / 'bear.json').exists()


def test_build_site_index_honors_pattern(tmp_path: Path):
    raw_root = tmp_path / 'raw'
    out_dir = tmp_path / 'index'

    write_json(raw_root / 'include.json', [task('tankeeah')])
    write_json(raw_root / 'nested' / 'exclude.json', [task('chignik')])

    summary = build_site_index(
        raw_root=raw_root,
        out_dir=out_dir,
        pattern='*.json',
    )

    assert summary['json_files_seen'] == 1
    assert set(summary['sites']) == {'tankeeah'}


def test_build_site_index_requires_existing_raw_root(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        build_site_index(
            raw_root=tmp_path / 'does-not-exist',
            out_dir=tmp_path / 'index',
        )
