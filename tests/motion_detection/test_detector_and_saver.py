from datetime import datetime, timezone
import errno
import json
import multiprocessing as mp
from pathlib import Path
import queue
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from pysalmcount import motion_detect_stream as md, utils

@pytest.mark.parametrize('kwargs', [
    {'morph_kernel_size': 0}, {'morph_kernel_size': 4}, {'erode_iter': -1}, {'dilate_iter': -1},
    {'fg_threshold': -1}, {'fg_threshold': 255}, {'min_contour_area': 0},
    {'min_contour_area_ratio': 0}, {'min_contour_area_ratio': 1},
    {'motion_trigger_seconds': 0}, {'warmup_seconds': -1}, {'composite': True}])
def test_invalid_detector_parameters_fail_before_capture(detector, kwargs):
    with pytest.raises(ValueError): detector.run(**kwargs)
    detector.dataloader.next_clip.assert_not_called()

def test_real_contours_obey_strict_area_threshold(detector):
    mask = np.zeros((64, 64), dtype=np.uint8)
    assert not detector.detect_motion(mask, min_area=100)
    mask[10:31, 10:31] = 255  # OpenCV contour area = 20 * 20.
    assert not detector.detect_motion(mask, min_area=400)
    assert detector.detect_motion(mask, min_area=399)

@pytest.mark.parametrize('head,tail,full', [(0,0,False), (3,0,True), (0,1,True), (2,0,False)])
def test_ring_full_wraparound(head, tail, full):
    assert md._ring_is_full(SimpleNamespace(value=head), SimpleNamespace(value=tail), 4) is full

def test_writable_directory_probe_cleans_up(tmp_path):
    target = tmp_path / 'nested/output'
    md.ensure_writable_dir(str(target), 'motion')
    assert target.is_dir() and list(target.iterdir()) == []

def test_disk_sync_failure_propagates_and_cleans_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(md.os, 'fsync', Mock(side_effect=OSError(errno.ENOSPC, 'disk full')))
    with pytest.raises(RuntimeError, match='not writable'): md.ensure_writable_dir(str(tmp_path), 'motion')
    assert list(tmp_path.iterdir()) == []

@pytest.mark.parametrize('exists', [False, True])
def test_missing_or_stalled_output_times_out(tmp_path, clock, exists):
    path = tmp_path / 'clip.mp4'
    if exists: path.write_bytes(b'initial')
    health = md.OutputFileHealth(str(path), 'motion', fail_after_s=5)
    health.check()
    clock.now += 5
    health.check()
    clock.now += .01
    with pytest.raises(RuntimeError, match='not growing' if exists else 'does not exist'): health.check()

def test_output_growth_resets_timeout(tmp_path, clock):
    path = tmp_path / 'clip.mp4'; path.write_bytes(b'a')
    health = md.OutputFileHealth(str(path), 'motion', 5); health.check()
    clock.now += 4; path.write_bytes(b'abc'); health.check()
    clock.now += 4; health.check()

@pytest.mark.parametrize('status,exitcode', [(True, None), (False, 2)])
def test_saver_errors_reach_detector(detector, status, exitcode):
    detector.status_q.close(); detector.status_q.join_thread()
    detector.status_q = queue.Queue()
    if status: detector.status_q.put((md.ERROR_CODE, 'write failed'))
    detector.video_saver = SimpleNamespace(exitcode=exitcode)
    try:
        with pytest.raises(RuntimeError, match='VideoSaver'): detector._raise_if_video_saver_failed()
    finally:
        detector.status_q = mp.Queue()

@pytest.fixture
def saver(tmp_path):
    raw = mp.Array('B', 4 * 2 * 2 * 3, lock=False)
    obj = md.VideoSaver(raw, (2,2,3), mp.Value('i', 0), mp.Value('i', 0), 4,
        tmp_path / 'motion_vids', mp.Event(), mp.Lock(), mp.Lock(), mp.Condition(), queue.Queue(),
        fps=10, save_prefix='device', orin=True, result_q=queue.Queue())
    obj.folder.mkdir()
    return obj

def test_shared_buffer_attaches_lazily_and_returns_copy(saver):
    assert saver.shared_frames is None
    saver._attach_shared_frames()
    saver.shared_frames[3] = 42; saver.tail.value = 3; saver.head.value = 0
    assert not saver._check_empty()
    frame = saver._get_frame()
    assert saver.tail.value == 0 and saver._check_empty()
    saver.shared_frames[3] = 99
    assert np.all(frame == 42)

def test_file_timestamp_advances_by_frame_count(saver):
    saver.is_video = True; saver.filename = 'device_20260101_235959_C.mp4'; saver.frame_count = 20
    assert Path(saver._get_md_filename(save_prefix='device')).name == 'device_20260102_000001_M.mp4'

def test_event_filename_collision_never_overwrites(saver):
    saver.event_id = 'event_abcdef'; saver.event_start_ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    saver.part_number = 3
    path = Path(saver._get_md_filename(save_prefix='device_top'))
    assert path.name == 'device_top_20260102_000000_Eabcdef_p003_M.mp4'
    path.write_bytes(b'original')
    alternate = Path(saver._get_md_filename(save_prefix='device_top'))
    assert alternate != path and alternate.name.startswith('collision_')
    assert path.read_bytes() == b'original'

def test_writer_open_failure_signals_parent(saver, monkeypatch):
    writer = Mock(); writer.isOpened.return_value = False
    monkeypatch.setattr(md.cv2, 'VideoWriter', Mock(return_value=writer))
    saver.run()
    assert saver.stop_event.is_set()
    status, payload = saver.status_q.get_nowait()
    assert status == md.ERROR_CODE and 'Could not open' in payload[0]
    writer.write.assert_not_called()

@pytest.mark.parametrize('composite', [False, True])
def test_saver_drains_preroll_and_writes_metadata(saver, monkeypatch, composite):
    saver.composite_mode = composite; saver.sonar = True
    saver._attach_shared_frames(); saver.shared_frames[0] = 10; saver.shared_frames[1] = 20
    saver.head.value = 2; saver.stop_event.set()
    if composite:
        saver.event_id = 'event_abcdef'; saver.cam_name = 'top'; saver.part_number = 1
        saver.event_start_ts = saver.part_start_ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    writer = Mock(); frames = []
    writer.write.side_effect = lambda frame: frames.append(frame.copy())
    monkeypatch.setattr(md.cv2, 'VideoWriter', Mock(return_value=writer))
    monkeypatch.setattr(utils, 'get_video_metadata', lambda path: utils.VideoMetadata(.2,'h264',2,2,2,0,'10/1','10/1'))
    saver.run()
    assert [int(f[0,0,0]) for f in frames] == [10, 20]
    writer.release.assert_called_once()
    assert saver._check_empty() and saver.status_q.empty()
    folder = 'motion_vids_parts_metadata' if composite else 'motion_vids_metadata'
    files = list((saver.folder.parent / folder).glob('*.json'))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload['nb_frames'] == 2
    settings = list((saver.folder.parent / md.DEVICE_SETTINGS_DIR).glob('*.json'))
    if composite:
        assert payload['pre_roll_frames'] == 2
        assert saver.result_q.get_nowait()['cam_name'] == 'top'
        assert settings == []
    else:
        assert json.loads(settings[0].read_text()) == md.SONAR_DEVICE_SETTINGS

@pytest.mark.parametrize('final', [False, True])
def test_stop_leaves_coordinator_only_on_final_and_terminates_stuck_saver(detector, final):
    detector.save_video = True; detector.motion_detected = True
    detector.coordinator = Mock(); detector.cam_name = 'top'
    process = Mock(); process.is_alive.return_value = True; process.exitcode = None
    detector.video_saver = process; detector.video_saver_stop_event = Mock()
    event = detector.video_saver_stop_event
    detector.stop_video_saving(final=final, join_timeout=.01)
    event.set.assert_called_once(); process.terminate.assert_called_once()
    assert process.join.call_count == 2
    assert detector.coordinator.leave_event.call_count == int(final)
    assert detector.video_saver is None and not detector.motion_detected

@pytest.mark.parametrize('leaky,block', [(False,True),(True,False)])
def test_cpu_pipeline_buffering_policy(leaky, block):
    pipeline = md.build_cpu_h264_writer('/tmp/output.mp4',10,1280,720,
        appsrc_block=block, queue_leaky=leaky, queue_buffers=4)
    assert f'block={str(block).lower()}' in pipeline
    assert f'max-bytes={1280*720*3*4}' in pipeline
    assert ('leaky=downstream' in pipeline) is leaky
    assert 'framerate=10/1' in pipeline and 'bitrate=1200' in pipeline

@pytest.mark.parametrize('probe_ok', [False, True])
def test_collect_completed_clip_emits_barrier_job(detector, probe_ok):
    # This flag exercises known versus unknown ClipInfo, not FFmpeg probing.
    detector.composite = True; detector.cam_name = 'top'
    detector.coordinator = Mock(); detector.composite_queue = queue.Queue()
    detector.result_q.close(); detector.result_q.join_thread(); detector.result_q = queue.Queue()
    info = md.ClipInfo('event', datetime.now(timezone.utc), 1, 'top')
    if probe_ok: detector._video_saver_clip_infos[('event',1)] = info
    detector.result_q.put({'event_id':'event','part_number':1,'cam_name':'top','path':'clip.mp4'})
    try:
        detector._collect_finished_clip()
        assert detector.coordinator.report_part_finished.call_count == int(probe_ok)
        assert detector.composite_queue.qsize() == int(probe_ok)
        assert detector._video_saver_clip_infos == {}
    finally: detector.result_q = mp.Queue()
