import csv
import json
from pathlib import Path

import pytest

from object_detection.metadata.index import (
    build_video_metadata_index,
    infer_fps,
    infer_s3_key,
    iter_task_items,
    parse_ffmpeg_rate,
    safe_float,
    write_video_metadata_index,
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


@pytest.mark.parametrize(
    ('value', 'default', 'expected'),
    [
        ('10', 0.0, 10.0),
        (5, 0.0, 5.0),
        (None, 7.0, 7.0),
        ('bad', 3.0, 3.0),
    ],
)
def test_safe_float(value, default, expected):
    assert safe_float(value, default) == expected


@pytest.mark.parametrize(
    ('rate', 'expected'),
    [
        ('30000/1001', pytest.approx(29.97002997)),
        ('30/1', 30.0),
        ('30', 30.0),
        (25, 25.0),
        ('10/0', 0.0),
        ('bad', 0.0),
        (None, 0.0),
    ],
)
def test_parse_ffmpeg_rate(rate, expected):
    assert parse_ffmpeg_rate(rate) == expected


def test_infer_fps_uses_expected_precedence():
    data = {
        'frames_per_second': '12',
        'metadata_video_r_frame_rate': '30/1',
        'metadata_video_avg_frame_rate': '25/1',
        'metadata_video_nb_frames': '1000',
        'metadata_video_duration': '100',
    }
    assert infer_fps(data) == 12.0

    data['frames_per_second'] = '0'
    assert infer_fps(data) == 30.0

    data['metadata_video_r_frame_rate'] = '0/1'
    assert infer_fps(data) == 25.0

    data['metadata_video_avg_frame_rate'] = 'bad'
    assert infer_fps(data) == 10.0


def test_infer_s3_key_requires_org_site_and_camera():
    data = {
        'metadata_file_organization_reference_string': 'GWA',
        'metadata_file_site_reference_string': 'stephenssmolt',
        'metadata_file_camera_reference_string': 'jetsonnx-0',
    }
    assert infer_s3_key(data, 'video_stem') == (
        'GWA/stephenssmolt/jetsonnx-0/motion_vids/video_stem.mp4'
    )

    missing = dict(data)
    missing['metadata_file_camera_reference_string'] = ''
    assert infer_s3_key(missing, 'video_stem') == ''


def test_iter_task_items_supports_dict_and_list_and_skips_invalid_json(tmp_path: Path):
    write_json(tmp_path / 'a.json', {'data': {'metadata_file_filename': 'a.mp4'}})
    write_json(
        tmp_path / 'b.json',
        [
            {'data': {'metadata_file_filename': 'b.mp4'}},
            'ignore me',
        ],
    )
    (tmp_path / 'broken.json').write_text('{not json', encoding='utf-8')

    items = list(iter_task_items(tmp_path))
    assert [item['data']['metadata_file_filename'] for item in items] == [
        'a.mp4',
        'b.mp4',
    ]


def test_build_video_metadata_index_extracts_fields_and_last_duplicate_wins(tmp_path: Path):
    write_json(
        tmp_path / 'a.json',
        {
            'data': {
                'metadata_file_filename': 'GWA-stephenssmolt-jetsonnx-0_20260101_000000_M.mp4',
                'frames_per_second': '10',
                'metadata_video_nb_frames': '100',
                'metadata_video_duration': '10',
                'metadata_video_width': '1280',
                'metadata_video_height': '720',
                'metadata_file_organization_reference_string': 'GWA',
                'metadata_file_site_reference_string': 'stephenssmolt',
                'metadata_file_camera_reference_string': 'jetsonnx-0',
            }
        },
    )

    # Sorted later and same stem, so this row replaces the first.
    write_json(
        tmp_path / 'z.json',
        {
            'data': {
                'metadata_file_filename': 'GWA-stephenssmolt-jetsonnx-0_20260101_000000_M.mp4',
                'frames_per_second': '30',
                'metadata_video_nb_frames': '300',
                'metadata_video_duration': '10',
                'metadata_video_width': '1920',
                'metadata_video_height': '1080',
                'metadata_file_organization_reference_string': 'GWA',
                'metadata_file_site_reference_string': 'stephenssmolt',
                'metadata_file_camera_reference_string': 'jetsonnx-0',
            }
        },
    )

    rows = build_video_metadata_index(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row['fps'] == '30.0'
    assert row['nb_frames'] == '300'
    assert row['width'] == '1920'
    assert row['height'] == '1080'
    assert row['site'] == 'stephenssmolt'
    assert row['s3_key'].endswith(
        'GWA-stephenssmolt-jetsonnx-0_20260101_000000_M.mp4'
    )


def test_build_video_metadata_index_falls_back_to_video_field(tmp_path: Path):
    write_json(
        tmp_path / 'a.json',
        {
            'data': {
                'video': 's3://bucket/HIRMD/tankeeah/jetson-0/motion_vids/HIRMD-tankeeah-jetson-0_20250101_000000_M.mp4',
                'metadata_video_nb_frames': '90',
                'metadata_video_duration': '9',
            }
        },
    )

    rows = build_video_metadata_index(tmp_path)
    assert len(rows) == 1
    assert rows[0]['video_stem'] == 'HIRMD-tankeeah-jetson-0_20250101_000000_M'
    assert rows[0]['fps'] == '10.0'


def test_write_video_metadata_index_writes_expected_columns(tmp_path: Path):
    out_csv = tmp_path / 'nested' / 'metadata.csv'
    rows = [{
        'video_stem': 'v',
        'fps': '10.0',
        'nb_frames': '100',
        'duration': '10.0',
        'width': '1280',
        'height': '720',
        'org': 'HIRMD',
        'site': 'tankeeah',
        'device': 'jetson-0',
        's3_key': 'HIRMD/tankeeah/jetson-0/motion_vids/v.mp4',
    }]

    write_video_metadata_index(rows, out_csv)

    with out_csv.open('r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        got = list(reader)
        assert reader.fieldnames == [
            'video_stem', 'fps', 'nb_frames', 'duration', 'width', 'height',
            'org', 'site', 'device', 's3_key',
        ]
    assert got == rows
