"""Check video syncing without remote calls or deprecated metadata requirements."""
from pathlib import Path
import os
import subprocess


def test_sync_video_upload_filter_backup_and_destination(tmp_path):
    repo = Path(os.environ.get('SALMON_REPO_ROOT', Path(__file__).resolve().parents[2]))
    script = repo/'utils/syncing/syncing.sh'
    drive = tmp_path/'hdd'
    device = drive/'UCHU/henderson/pi-0'
    (device/'motion_vids/20260720/1400/CH01').mkdir(parents=True)
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
    assert str(device/'motion_vids_backup')+'/' in calls
    assert 'aws:example/UCHU/henderson/pi-0/' in calls

