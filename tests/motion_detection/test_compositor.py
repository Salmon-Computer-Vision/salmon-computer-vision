from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
from unittest.mock import Mock
import pytest
from pysalmcount import clip_compositor as cc, utils

@pytest.fixture
def job(tmp_path):
    parts = tmp_path / 'motion_vids_parts'
    parts.mkdir()
    sources = []
    for cam in ['top', 'bottom']:
        path = parts / f'device_{cam}_20260102_030405_Eabcdef_p001_M.mp4'
        path.write_bytes(b'source')
        cc._write_json(cc._parts_metadata_path(path), {
            'event_id': '20260102T030405Z_abcdef', 'part_number': 1,
            'part_start_ts': '2026-01-02T03:04:05+00:00'})
        sources.append(cc.CompositeSource(cam, path))
    return cc.CompositeJob('20260102T030405Z_abcdef', 1,
        datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc), sources,
        tmp_path / 'motion_vids', 'device', 10, False)

def metadata(n=10):
    return utils.VideoMetadata(n / 10, 'h264', n, 1280, 1440, 0, '10/1', '10/1')

def test_end_alignment_trims_front_and_keeps_missing_row(job, monkeypatch):
    job = replace(job, sources=job.sources + [cc.CompositeSource('missing', None)])
    monkeypatch.setattr(cc.utils, 'get_video_metadata', Mock(side_effect=[metadata(20), metadata(12)]))
    result = cc.calculate_end_alignment(job)
    assert result == cc.EndAlignment([20, 12, None], [8, 0, 0], 12)

@pytest.mark.parametrize('bad_metadata', [None, metadata(0), metadata(-1)])
def test_bad_source_probe_rejected(job, monkeypatch, bad_metadata):
    monkeypatch.setattr(cc.utils, 'get_video_metadata', lambda p: bad_metadata)
    with pytest.raises(RuntimeError):
        cc.calculate_end_alignment(job)

@pytest.mark.parametrize('sources', [[], [cc.CompositeSource('absent', None)]])
def test_no_present_source_rejected(job, sources):
    with pytest.raises(ValueError):
        cc.calculate_end_alignment(replace(job, sources=sources))

def test_ffmpeg_command_alignment_and_black_row(job):
    job = replace(job, sources=[job.sources[0], cc.CompositeSource('missing', None)])
    command = cc.build_ffmpeg_cmd(job, Path('output with spaces.mp4'), cc.EndAlignment([20, None], [8, 0], 12))
    filters = command[command.index('-filter_complex') + 1]
    assert 'trim=start_frame=8:end_frame=20' in filters
    assert 'trim=start_frame=0:end_frame=12' in filters
    assert 'vstack=inputs=2:shortest=1' in filters
    assert 'color=c=black:s=1280x720:r=10' in command
    assert command[command.index('-t') + 1] == '1.200000'
    assert command[command.index('-frames:v') + 1] == '12'
    assert command[-1] == 'output with spaces.mp4'

@pytest.mark.parametrize('fps', [0, -1])
def test_invalid_output_fps(job, fps):
    with pytest.raises(ValueError, match='positive'):
        cc.build_ffmpeg_cmd(replace(job, fps=fps), Path('out.mp4'))

def test_output_name_preserves_collision(job):
    job.out_dir.mkdir()
    original = cc.composite_output_path(job)
    original.write_bytes(b'keep me')
    alternate = cc.composite_output_path(job)
    assert alternate != original
    assert alternate.name.startswith('collision_')
    assert original.read_bytes() == b'keep me'
    with pytest.raises(ValueError, match='timezone-aware'):
        cc.composite_output_path(replace(job, part_start_ts=datetime(2026, 1, 1)))

def test_success_publishes_metadata_before_deleting_sources(job, monkeypatch):
    monkeypatch.setattr(cc.utils, 'get_video_metadata', lambda p: metadata())
    def encode(command, **kwargs):
        assert kwargs['check'] is True
        assert all(s.path.exists() for s in job.sources)
        Path(command[-1]).write_bytes(b'encoded')
    monkeypatch.setattr(cc.subprocess, 'run', encode)
    out = cc.run_composite(job)
    assert out.read_bytes() == b'encoded'
    payload = json.loads((out.parent.parent / 'motion_vids_metadata' / f'{out.stem}.json').read_text())
    assert payload['cam_order'] == ['top', 'bottom']
    assert payload['frame_alignment'] == 'end'
    assert payload['aligned_frame_count'] == 10
    assert payload['event_id'] == job.event_id
    assert all(not s.path.exists() and not cc._parts_metadata_path(s.path).exists() for s in job.sources)
    assert not list(out.parent.glob('.*.tmp.mp4'))

@pytest.mark.parametrize('failure', ['encode', 'output_probe', 'metadata_write'])
def test_failure_preserves_source_clips_and_sidecars(job, monkeypatch, failure):
    def encode(command, **kwargs):
        Path(command[-1]).write_bytes(b'partial')
        if failure == 'encode':
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(cc.subprocess, 'run', encode)
    monkeypatch.setattr(cc.utils, 'get_video_metadata',
        lambda p: None if failure == 'output_probe' and Path(p).parent == job.out_dir else metadata())
    if failure == 'metadata_write':
        monkeypatch.setattr(cc, '_write_json', Mock(side_effect=OSError('disk full')))
    with pytest.raises((RuntimeError, OSError, subprocess.CalledProcessError)):
        cc.run_composite(job)
    assert all(s.path.exists() and cc._parts_metadata_path(s.path).exists() for s in job.sources)
    assert not list(job.out_dir.glob('.*.tmp.mp4'))

def recover(job, **kwargs):
    return cc.find_stale_composite_jobs(job.sources[0].path.parent,
        ['bottom', 'top', 'missing'], job.out_dir, 'device', 10, False, 60, now=1000, **kwargs)

def test_recovery_waits_until_every_source_is_stale(job):
    os.utime(job.sources[0].path, (800, 800))
    os.utime(job.sources[1].path, (950, 950))
    assert recover(job) == []
    os.utime(job.sources[1].path, (940, 940))
    jobs = recover(job)
    assert len(jobs) == 1
    assert jobs[0].event_id == job.event_id
    assert [s.cam_name for s in jobs[0].sources] == ['bottom', 'top', 'missing']
    assert jobs[0].sources[2].path is None

@pytest.mark.parametrize('metadata_state', ['missing', 'malformed'])
def test_recovery_without_metadata(job, metadata_state):
    for source in job.sources:
        os.utime(source.path, (800, 800))
        sidecar = cc._parts_metadata_path(source.path)
        if metadata_state == 'missing': sidecar.unlink()
        else: sidecar.write_text('{broken')
    jobs = recover(job)
    assert len(jobs) == 1
    assert jobs[0].event_id == 'recovered_20260102T030405_abcdef'
    assert jobs[0].part_start_ts.tzinfo is not None

def test_recovery_rejects_conflicting_event_ids(job):
    for source in job.sources:
        os.utime(source.path, (800, 800))
    sidecar = cc._parts_metadata_path(job.sources[0].path)
    data = json.loads(sidecar.read_text()); data['event_id'] = 'different'
    sidecar.write_text(json.dumps(data))
    assert recover(job) == []

def test_worker_continues_after_failed_job(job, monkeypatch):
    q = queue.Queue()
    for item in [job, job, None]: q.put(item)
    run = Mock(side_effect=[RuntimeError('failed'), None])
    monkeypatch.setattr(cc, 'run_composite', run)
    cc.CompositorWorker(q).run()
    assert run.call_count == 2
