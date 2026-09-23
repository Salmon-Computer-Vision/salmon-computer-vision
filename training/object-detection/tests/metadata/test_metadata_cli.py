import csv
import json
import sys
from pathlib import Path

from object_detection.metadata.cli import main as metadata_index_main
from object_detection.metadata.filter_cli import main as filter_main
from object_detection.metadata.site_index_cli import main as site_index_main


def test_metadata_index_cli_smoke(tmp_path: Path, monkeypatch, capsys):
    json_root = tmp_path / 'raw'
    json_root.mkdir()
    out_csv = tmp_path / 'metadata.csv'

    (json_root / 'tasks.json').write_text(
        json.dumps({
            'data': {
                'metadata_file_filename': 'HIRMD-tankeeah-jetson-0_20250101_000000_M.mp4',
                'frames_per_second': 10,
                'metadata_file_organization_reference_string': 'HIRMD',
                'metadata_file_site_reference_string': 'tankeeah',
                'metadata_file_camera_reference_string': 'jetson-0',
            }
        }),
        encoding='utf-8',
    )

    monkeypatch.setattr(sys, 'argv', [
        'prog', '--json-dir', str(json_root), '--out-csv', str(out_csv)
    ])
    metadata_index_main()

    assert out_csv.exists()
    assert 'indexed_videos=1' in capsys.readouterr().out


def test_filter_cli_smoke(tmp_path: Path, monkeypatch, capsys):
    input_csv = tmp_path / 'metadata.csv'
    out_csv = tmp_path / 'tankeeah.csv'

    with input_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['video_stem', 'site', 's3_key'])
        writer.writeheader()
        writer.writerow({'video_stem': 'a', 'site': 'tankeeah', 's3_key': ''})
        writer.writerow({'video_stem': 'b', 'site': 'bear', 's3_key': ''})

    monkeypatch.setattr(sys, 'argv', [
        'prog', '--input-csv', str(input_csv), '--site', 'tankeeah',
        '--out-csv', str(out_csv),
    ])
    filter_main()

    assert out_csv.exists()
    assert "Wrote 1 metadata rows for site 'tankeeah'" in capsys.readouterr().out


def test_site_index_cli_smoke_with_warning(tmp_path: Path, monkeypatch, capsys):
    raw_root = tmp_path / 'raw'
    raw_root.mkdir()
    out_dir = tmp_path / 'site_index'

    (raw_root / 'tasks.json').write_text(
        json.dumps([
            {'data': {
                'metadata_file_site_reference_string': 'tankeeah',
                'metadata_file_organization_reference_string': 'HIRMD',
                'metadata_file_camera_reference_string': 'jetson-0',
            }},
            {'data': {}},
        ]),
        encoding='utf-8',
    )

    monkeypatch.setattr(sys, 'argv', [
        'prog', '--json-root', str(raw_root), '--out-dir', str(out_dir)
    ])
    site_index_main()

    stdout = capsys.readouterr().out
    assert 'Indexed 1 JSON files into 1 sites' in stdout
    assert 'tankeeah: 1 export(s), 1 task(s)' in stdout
    assert 'WARNING: 1 tasks were missing' in stdout
    assert (out_dir / 'tankeeah.json').exists()
    assert (out_dir / 'summary.json').exists()
