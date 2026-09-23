import csv
from pathlib import Path

import pytest

from object_detection.metadata.filter import infer_site, filter_metadata_csv_by_site


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ('column', 'value'),
    [
        ('site', 'tankeeah'),
        ('site_name', 'kitwanga'),
        ('metadata_file_site_reference_string', 'chignik'),
    ],
)
def test_infer_site_from_explicit_columns(column: str, value: str):
    row = {
        column: f'  {value}  ',
        's3_key': 'HIRMD/wrong-site/jetson-0/motion_vids/video.mp4',
    }
    assert infer_site(row) == value


def test_infer_site_explicit_column_precedence():
    row = {
        'site': 'tankeeah',
        'site_name': 'bear',
        'metadata_file_site_reference_string': 'chignik',
    }
    assert infer_site(row) == 'tankeeah'


def test_infer_site_from_plain_s3_key():
    assert infer_site({
        's3_key': 'HIRMD/tankeeah/jetson-0/motion_vids/video.mp4'
    }) == 'tankeeah'


def test_infer_site_from_s3_uri():
    assert infer_site({
        's3_key': 's3://bucket-name/GWA/stephenssmolt/jetsonnx-0/motion_vids/video.mp4'
    }) == 'stephenssmolt'


@pytest.mark.parametrize(
    'row',
    [
        {},
        {'s3_key': ''},
        {'s3_key': 'only-one-component'},
        {'s3_key': 's3://bucket-only'},
        {'s3_key': 's3://bucket/ORG'},
    ],
)
def test_infer_site_returns_none_when_site_cannot_be_inferred(row):
    assert infer_site(row) is None


def test_filter_metadata_csv_by_site_case_insensitive_sorted_and_header_preserved(tmp_path: Path):
    input_csv = tmp_path / 'all.csv'
    output_csv = tmp_path / 'nested' / 'tankeeah.csv'
    fieldnames = ['video_stem', 'fps', 'site', 's3_key', 'extra']

    write_csv(
        input_csv,
        [
            {
                'video_stem': 'Z_video',
                'fps': '10',
                'site': 'TANKEEAH',
                's3_key': 'HIRMD/tankeeah/j0/motion_vids/Z_video.mp4',
                'extra': 'z',
            },
            {
                'video_stem': 'B_video',
                'fps': '20',
                'site': 'bear',
                's3_key': 'HIRMD/bear/j0/motion_vids/B_video.mp4',
                'extra': 'b',
            },
            {
                'video_stem': 'A_video',
                'fps': '30',
                'site': 'tankeeah',
                's3_key': 'HIRMD/tankeeah/j1/motion_vids/A_video.mp4',
                'extra': 'a',
            },
        ],
        fieldnames,
    )

    count = filter_metadata_csv_by_site(
        input_csv=input_csv,
        site='Tankeeah',
        out_csv=output_csv,
    )

    assert count == 2
    assert output_csv.exists()

    with output_csv.open('r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert reader.fieldnames == fieldnames

    assert [row['video_stem'] for row in rows] == ['A_video', 'Z_video']
    assert [row['extra'] for row in rows] == ['a', 'z']


def test_filter_metadata_csv_by_site_uses_s3_fallback_and_skips_uninferable_rows(tmp_path: Path):
    input_csv = tmp_path / 'all.csv'
    output_csv = tmp_path / 'stephenssmolt.csv'
    fieldnames = ['video_stem', 'fps', 's3_key']

    write_csv(
        input_csv,
        [
            {
                'video_stem': 'wanted',
                'fps': '10',
                's3_key': 'GWA/stephenssmolt/jetsonnx-0/motion_vids/wanted.mp4',
            },
            {
                'video_stem': 'unknown',
                'fps': '10',
                's3_key': '',
            },
        ],
        fieldnames,
    )

    count = filter_metadata_csv_by_site(
        input_csv=input_csv,
        site='stephenssmolt',
        out_csv=output_csv,
    )

    assert count == 1
    with output_csv.open('r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert [row['video_stem'] for row in rows] == ['wanted']


def test_filter_metadata_csv_by_site_raises_when_no_rows_match(tmp_path: Path):
    input_csv = tmp_path / 'all.csv'
    output_csv = tmp_path / 'missing.csv'
    write_csv(
        input_csv,
        [{'video_stem': 'a', 'site': 'bear', 's3_key': ''}],
        ['video_stem', 'site', 's3_key'],
    )

    with pytest.raises(RuntimeError, match="No metadata rows found for site 'chignik'"):
        filter_metadata_csv_by_site(
            input_csv=input_csv,
            site='chignik',
            out_csv=output_csv,
        )

    assert not output_csv.exists()


def test_filter_metadata_csv_by_site_raises_on_missing_header(tmp_path: Path):
    input_csv = tmp_path / 'empty.csv'
    output_csv = tmp_path / 'out.csv'
    input_csv.write_text('', encoding='utf-8')

    with pytest.raises(ValueError, match='No CSV header'):
        filter_metadata_csv_by_site(
            input_csv=input_csv,
            site='tankeeah',
            out_csv=output_csv,
        )
