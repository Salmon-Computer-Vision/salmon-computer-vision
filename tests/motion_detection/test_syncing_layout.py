"""Checks the syncing script without contacting any remote service."""
from pathlib import Path
import os
import subprocess


def test_sync_upload_filters_and_metadata_backups(tmp_path):
    repo = Path(os.environ.get('SALMON_REPO_ROOT', Path(__file__).resolve().parents[2]))
    script = repo/'utils/syncing/syncing.sh'
    drive = tmp_path/'hdd'
    device = drive/'UCHU/henderson/UCHU-henderson-pi-0'
    (device/'motion_vids/20260720/1400/CH01').mkdir(parents=True)
    (device/'motion_vids_metadata/20260720/1400/CH01').mkdir(parents=True)
    binaries = tmp_path/'bin'
    binaries.mkdir()
    log = tmp_path/'calls'
    (binaries/'rclone').write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$CALL_LOG"\n')
    (binaries/'sleep').write_text('#!/bin/sh\nexit 0\n')
    for p in binaries.iterdir():
        p.chmod(0o755)
    subprocess.run(['bash', str(script), '-d', str(drive), '-o', 'UCHU',
                    '-s', 'henderson', '-b', 'example', '-c', '/config/test',
                    '-f', '0'], check=True,
                   env={**os.environ, 'PATH': str(binaries)+':'+os.environ['PATH'],
                        'CALL_LOG': str(log)}, capture_output=True)
    calls = log.read_text()
    assert '+ /motion_vids/**' in calls
    assert '+ /motion_vids_metadata/**' in calls
    assert str(device/'motion_vids_metadata_backup')+'/' in calls
    assert 'aws:example/UCHU/henderson/UCHU-henderson-pi-0/' in calls


def test_nested_backup_cleanup_removes_matching_metadata_only(tmp_path):
    repo = Path(os.environ.get('SALMON_REPO_ROOT', Path(__file__).resolve().parents[2]))
    script = (repo/'utils/syncing/syncing.sh').read_text()
    function = script.split('delete_matching_backup_metadata() {', 1)[1].split('\n}\n', 1)[0]
    device = tmp_path/'device'
    video = device/'motion_vids_backup/20260720/1400/CH01/clip.mp4'
    metadata = device/'motion_vids_metadata_backup/20260720/1400/CH01/clip.json'
    unrelated = metadata.with_name('other.json')
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{}')
    unrelated.write_text('{}')
    subprocess.run(['bash', '-c', 'delete_matching_backup_metadata() {'+function+
                    '\n}\ndelete_matching_backup_metadata "$1"', 'test', str(video)], check=True)
    assert not metadata.exists()
    assert unrelated.exists()
