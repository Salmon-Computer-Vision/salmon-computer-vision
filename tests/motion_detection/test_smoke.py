"""Real local integrations; never open RTSP cameras or send health pings."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import pytest
import cv2
from pysalmcount import clip_compositor as cc, motion_detect_stream as md, utils, videoloader as vl
from pysalmcount.dataloader import Item

pytestmark = pytest.mark.smoke

@pytest.fixture
def ffmpeg_available():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Install ffmpeg and ffprobe to run media smoke tests')
    result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=10, check=True)
    if 'libx264' not in result.stdout: pytest.skip('FFmpeg lacks libx264')

def make_clip(path, color, frames):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        f'color=c={color}:s=1280x720:r=10', '-frames:v', str(frames),
        '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(path)],
        check=True, capture_output=True, timeout=20)

@pytest.mark.parametrize('missing', [False, True])
def test_real_ffmpeg_composite_and_probe(tmp_path, ffmpeg_available, missing):
    parts = tmp_path / 'motion_vids_parts'; parts.mkdir()
    top = parts / 'top.mp4'; bottom = parts / 'bottom.mp4'
    make_clip(top, 'red', 6)
    if not missing: make_clip(bottom, 'blue', 4)
    job = cc.CompositeJob('test_abcdef', 1, datetime.now(timezone.utc),
        [cc.CompositeSource('top', top), cc.CompositeSource('bottom', None if missing else bottom)],
        tmp_path / 'motion_vids', 'test', 10, False)
    output = cc.run_composite(job)
    metadata = utils.get_video_metadata(output)
    assert (metadata.width, metadata.height) == (1280, 1440)
    assert metadata.nb_frames == (6 if missing else 4)
    cap = cv2.VideoCapture(str(output))
    try:
        ok, frame = cap.read()
        assert ok
        upper = frame[100:600,100:1100].mean(axis=(0,1))
        lower = frame[820:1320,100:1100].mean(axis=(0,1))
        assert upper[2] > 200 and upper[0] < 20  # BGR: red on top.
        if missing: assert max(lower) < 10
        else: assert lower[0] > 200 and lower[2] < 20  # Blue below.
    finally: cap.release()
    assert not top.exists()
    assert not bottom.exists()

def test_real_video_loader_file_sampling(tmp_path, ffmpeg_available):
    path = tmp_path / 'input.mp4'; make_clip(path, 'green', 10)
    loader = vl.VideoLoader([str(path)], target_fps=5, buffer_size=2)
    try:
        assert loader.next_clip() == path
        frames = list(loader.items())
        assert len(frames) == 5
        assert all(item.frame.shape == (720,1280,3) for item in frames)
        assert not loader.thread.is_alive()
        assert not loader.cap.isOpened()
    finally: loader.close()

def test_cli_help_exits_without_hardware(cli):
    package_root = str(Path(md.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=package_root + os.pathsep + os.environ.get('PYTHONPATH',''))
    result = subprocess.run([sys.executable, cli.__file__, '--help'], capture_output=True,
        text=True, timeout=15, env=env)
    assert result.returncode == 0, result.stderr
    assert '--multi-camera' in result.stdout and '--fps' in result.stdout

def test_detector_loop_triggers_and_finalizes_at_eof(detector, monkeypatch):
    # Keep real run loop, resize, morphology and contour detection. Only the
    # background mask is controlled to make trigger timing deterministic.
    class Loader:
        closed = False
        def next_clip(self): return Path('synthetic.mp4')
        def fps(self): return 2
        def items(self):
            for i in range(4): yield Item(np.zeros((32,32,3), np.uint8), 4)
        def close(self): self.closed = True
    loader = Loader(); detector.dataloader = loader
    masks = [np.zeros((720,1280), np.uint8) for _ in range(4)]
    for mask in masks[2:]: mask[100:300,100:300] = 255
    class Background:
        def apply(self, frame): return masks.pop(0)
    monkeypatch.setattr(md.cv2, 'createBackgroundSubtractorMOG2', lambda **kwargs: Background())
    monkeypatch.setattr(utils, 'ping_in_background', lambda url: None)
    result = detector.run(fps=2, warmup_seconds=0, motion_trigger_seconds=1,
        morph_kernel_size=1, erode_iter=0, dilate_iter=0, min_contour_area=100)
    assert result == {'synthetic.mp4': [(3, 4)]}
    assert loader.closed and not detector.motion_detected

@pytest.mark.hardware
def test_deployment_gstreamer_cpu_writer(tmp_path):
    if os.environ.get('SALMON_TEST_HARDWARE') != '1':
        pytest.skip('Set SALMON_TEST_HARDWARE=1 inside the Pi/Jetson deployment environment')
    assert 'GStreamer:                   YES' in cv2.getBuildInformation() or __import__('re').search(r'GStreamer:\s+YES', cv2.getBuildInformation())
    path = tmp_path / 'cpu-smoke.mp4'
    pipeline = md.build_cpu_h264_writer(str(path), 10, 320, 240)
    writer = cv2.VideoWriter(pipeline, cv2.CAP_GSTREAMER, 0, 10, (320,240))
    try:
        assert writer.isOpened(), pipeline
        for i in range(10): writer.write(np.full((240,320,3), i * 20, np.uint8))
    finally: writer.release()
    metadata = utils.get_video_metadata(path)
    assert metadata is not None and metadata.nb_frames == 10 and metadata.codec_name == 'h264'
