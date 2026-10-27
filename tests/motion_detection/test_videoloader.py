from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pytest
import cv2
from pysalmcount import videoloader as vl

@pytest.fixture
def loader():
    result = vl.VideoLoader([], buffer_size=100)
    yield result
    result.close()

def test_live_queue_drops_oldest(clock):
    loader = vl.VideoLoader([], buffer_size=2)
    try:
        for value in [1, 2, 3]: assert loader._put_live_frame_latest(value)
        assert [loader.frame_buffer.get_nowait(), loader.frame_buffer.get_nowait()] == [2, 3]
        assert loader.queue_drop_count == 1
    finally:
        loader.close()

@pytest.mark.parametrize('source,count,expected', [
    ('rtsp://example.invalid/live', 0, False), ('0', 0, False),
    ('clip.MP4', 0, True), ('clip.mkv', 0, True), ('no-extension', 10, True)])
def test_source_classification(loader, source, count, expected):
    loader.cap = Mock(); loader.cap.get.return_value = count
    assert loader._detect_source_type(source) is expected

@pytest.mark.parametrize('target,expected', [(None, list(range(12))), (30, list(range(12))), (10, [1,3,5,7,9,11])])
def test_file_sampling_preserves_order_and_sentinel(loader, target, expected, clock):
    loader.is_video = True; loader.vid_fps = 20; loader.target_fps = target
    loader.cap = Mock()
    loader.cap.read.side_effect = [(True, i) for i in range(12)] + [(False, None)]
    loader._read_frames()
    actual = []
    while not loader.frame_buffer.empty(): actual.append(loader.frame_buffer.get_nowait())
    assert actual == expected + [None]

def test_live_sampling_resyncs_after_stall(loader, clock):
    loader.is_video = False; loader.vid_fps = 90000; loader.target_fps = 2
    samples = iter([(100, 0), (100.1, 1), (100.5, 2), (105, 3), (105.1, 4), (105.5, 5)])
    def read():
        try: clock.now, value = next(samples)
        except StopIteration: return False, None
        return True, value
    loader.cap = Mock(); loader.cap.read.side_effect = read
    loader._read_frames()
    actual = []
    while not loader.frame_buffer.empty(): actual.append(loader.frame_buffer.get_nowait())
    assert actual == [0, 2, 3, 5, None]

def test_live_eof_full_queue_inserts_sentinel(loader, clock):
    import queue
    loader.frame_buffer = queue.Queue(maxsize=1)
    loader.frame_buffer.put('old')
    loader.is_video = False
    loader.cap = Mock(); loader.cap.read.return_value = (False, None)
    loader._read_frames()
    assert loader.frame_buffer.get_nowait() is None

def test_network_capture_uses_timeouts(loader, monkeypatch):
    monkeypatch.setattr(cv2, 'CAP_PROP_OPEN_TIMEOUT_MSEC', 53, raising=False)
    monkeypatch.setattr(cv2, 'CAP_PROP_READ_TIMEOUT_MSEC', 54, raising=False)
    constructor = Mock()
    monkeypatch.setattr(cv2, 'VideoCapture', constructor)
    loader._open_ffmpeg_capture('rtsp://example.invalid/live')
    constructor.assert_called_once_with('rtsp://example.invalid/live', cv2.CAP_FFMPEG, [53, 5000, 54, 5000])

@pytest.mark.parametrize('error', [TypeError('old bindings'), cv2.error('unsupported')])
def test_timeout_constructor_fallback(loader, monkeypatch, error):
    monkeypatch.setattr(cv2, 'CAP_PROP_OPEN_TIMEOUT_MSEC', 53, raising=False)
    monkeypatch.setattr(cv2, 'CAP_PROP_READ_TIMEOUT_MSEC', 54, raising=False)
    capture = Mock()
    constructor = Mock(side_effect=[error, capture])
    monkeypatch.setattr(cv2, 'VideoCapture', constructor)
    assert loader._open_ffmpeg_capture('rtsp://example.invalid/live') is capture
    assert constructor.call_args.args == ('rtsp://example.invalid/live', cv2.CAP_FFMPEG)

def test_file_capture_has_no_network_timeout_arguments(loader, monkeypatch):
    constructor = Mock(); monkeypatch.setattr(cv2, 'VideoCapture', constructor)
    loader._open_ffmpeg_capture('clip.mp4')
    constructor.assert_called_once_with('clip.mp4', cv2.CAP_FFMPEG)

@pytest.mark.parametrize('reported,target,expected', [(90000, 8, 8), (0, None, 10), (25, 10, 25)])
def test_live_fps_fallback_does_not_consume_frames(monkeypatch, reported, target, expected):
    loader = vl.VideoLoader(['rtsp://example.invalid/live'], target_fps=target)
    cap = Mock(); cap.get.side_effect = lambda key: reported if key == cv2.CAP_PROP_FPS else 0
    monkeypatch.setattr(loader, '_open_ffmpeg_capture', lambda src: cap)
    thread = Mock(); thread.is_alive.return_value = False
    monkeypatch.setattr(vl, 'Thread', Mock(return_value=thread))
    try:
        loader.next_clip()
        assert loader.fps() == expected
        cap.read.assert_not_called()
        thread.start.assert_called_once()
    finally: loader.close()

def test_open_failure_does_not_start_thread(monkeypatch):
    loader = vl.VideoLoader(['missing.mp4'])
    cap = Mock(); cap.isOpened.return_value = False
    monkeypatch.setattr(loader, '_open_ffmpeg_capture', lambda src: cap)
    try:
        with pytest.raises(vl.VideoCaptureError): loader.next_clip()
        assert loader.thread is None
    finally: loader.close()

def test_items_yield_frames_and_release(loader):
    loader.cur_clip = Path('clip.mp4'); loader.total_frames = 1
    loader.cap = Mock()
    frame = np.zeros((2, 2, 3), np.uint8)
    loader.frame_buffer.put(frame); loader.frame_buffer.put(None)
    items = list(loader.items())
    assert len(items) == 1 and items[0].frame is frame and items[0].num_items == 1
    loader.cap.release.assert_called_once()
