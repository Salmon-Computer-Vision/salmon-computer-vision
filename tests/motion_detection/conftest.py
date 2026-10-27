"""Import the checkout under test, never a bundled copy or installed release."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(os.environ.get('SALMON_REPO_ROOT', Path(__file__).resolve().parents[2])).resolve()
PACKAGE = ROOT / 'training/pysalmcount'
if not (PACKAGE / 'pysalmcount/motion_detect_stream.py').is_file():
    raise pytest.UsageError('Run from the salmon-computer-vision checkout, or set SALMON_REPO_ROOT')
sys.path.insert(0, str(PACKAGE))

@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location('motion_cli_under_test', ROOT / 'training/tools/run_motion_detect_rtsp.py')
    module = importlib.util.module_from_spec(spec)
    import logging
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        for handler in root.handlers[:]:
            if handler not in handlers:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)

@pytest.fixture
def clock(monkeypatch):
    # Patch the module reference, not time.monotonic globally (pytest uses it).
    from pysalmcount import motion_detect_stream as md, videoloader as vl
    import time
    fake = SimpleNamespace(now=100.0)
    proxy = SimpleNamespace(**{name: getattr(time, name) for name in dir(time) if not name.startswith('__')})
    proxy.monotonic = lambda: fake.now
    monkeypatch.setattr(md, 'time', proxy)
    monkeypatch.setattr(vl, 'time', proxy)
    return fake

@pytest.fixture(autouse=True)
def no_healthcheck_network(monkeypatch):
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not make HTTP requests')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)

@pytest.fixture
def detector(tmp_path):
    from pysalmcount.motion_detect_stream import MotionDetector
    from unittest.mock import Mock
    det = MotionDetector(Mock(), tmp_path, save_video=False, save_cont_video=False)
    yield det
    for q in (det.status_q, det.result_q):
        q.close()
        q.join_thread()
