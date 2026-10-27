"""Regression tests: both fixed defects must remain ordinary test failures."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import cv2
import pytest
from pysalmcount import motion_detect_stream as md, videoloader as vl

@pytest.mark.parametrize('source,count,expected', [
    ('example.mp4', 10, True), ('rtsp://example.invalid/live', 0, False)])
def test_is_video_remains_callable_after_open(monkeypatch, source, count, expected):
    loader = vl.VideoLoader([source])
    cap = Mock()
    cap.get.side_effect = lambda key: count if key == cv2.CAP_PROP_FRAME_COUNT else 10
    monkeypatch.setattr(loader, '_open_ffmpeg_capture', lambda source: cap)
    thread = Mock(); thread.is_alive.return_value = False
    monkeypatch.setattr(vl, 'Thread', Mock(return_value=thread))
    try:
        loader.next_clip()
        assert loader.is_video() is expected
    finally: loader.close()

def test_detection_without_saving_reaches_eof(tmp_path):
    # subprocess.run kills and reaps the child on timeout. The outer pytest
    # timeout remains a final backstop; either timeout is a test failure.
    code = '''
from pathlib import Path
import sys
import numpy as np
from pysalmcount import motion_detect_stream as md, utils
from pysalmcount.dataloader import Item
class Loader:
    def next_clip(self): return Path('synthetic.mp4')
    def fps(self): return 2
    def items(self):
        for i in range(8): yield Item(np.zeros((16,16,3),np.uint8),8)
    closed = False
    def close(self): self.closed = True
utils.ping_in_background = lambda url: None
loader = Loader()
det = md.MotionDetector(loader, sys.argv[1], save_video=False, save_cont_video=False)
det.detect_motion = lambda *a, **kw: True
try:
    result = det.run(fps=2, warmup_seconds=0, motion_trigger_seconds=.5)
    assert result == {'synthetic.mp4': [(0, 8)]}, result
    assert loader.closed
    assert not det.motion_detected
    assert det.video_saver is None
finally:
    for q in (det.status_q, det.result_q):
        q.close(); q.join_thread()
'''
    package_root = str(Path(md.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=package_root + os.pathsep + os.environ.get('PYTHONPATH', ''))
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
        capture_output=True, text=True, timeout=8, env=env)
    assert result.returncode == 0, result.stderr
