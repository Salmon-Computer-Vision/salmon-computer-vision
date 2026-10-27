"""Rotate decoded frames before resize, detection, and either recording path."""
import argparse
import logging
from pathlib import Path
import runpy
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
from pysalmcount import motion_detect_stream as md, utils
from pysalmcount.dataloader import Item


@pytest.mark.parametrize('direction,k', [(None, 0), ('cw', -1), ('ccw', 1)])
def test_rotation_reaches_detector_continuous_writer_and_motion_ring(detector, monkeypatch, direction, k):
    # Non-square input with distinct pixels makes direction and ordering observable.
    frames = [np.arange(18, dtype=np.uint8).reshape(3, 2, 3) + offset for offset in (0, 30)]
    loader = Mock()
    loader.next_clip.return_value = Path('rotated.mp4')
    loader.fps.return_value = 2
    loader.items.return_value = iter([Item(frame, 2) for frame in frames])
    detector.dataloader = loader
    detector.save_cont_video = True
    seen = []
    background = Mock()
    background.apply.side_effect = lambda frame: (seen.append(frame.copy()) or np.zeros(frame.shape[:2], np.uint8))
    monkeypatch.setattr(md.cv2, 'createBackgroundSubtractorMOG2', lambda **kw: background)
    writer = Mock()
    written = []
    writer.write.side_effect = lambda frame: written.append(frame.copy())
    monkeypatch.setattr(md.cv2, 'VideoWriter', Mock(return_value=writer))
    monkeypatch.setattr(utils, 'ping_in_background', lambda url: None)
    real_array = md.Array
    buffers = []
    def allocate(*args, **kwargs):
        raw = real_array(*args, **kwargs)
        buffers.append(raw)
        return raw
    monkeypatch.setattr(md, 'Array', allocate)
    original = [frame.copy() for frame in frames]
    kwargs = {} if direction is None else {'rotate_90': direction}
    detector.run(fps=2, warmup_seconds=0, **kwargs)
    ring = np.ndarray((4,720,1280,3), dtype=np.uint8, buffer=buffers[0])
    assert len(seen) == len(written) == 2
    for index, frame in enumerate(original):
        expected = cv2.resize(np.rot90(frame, k), (1280,720), interpolation=cv2.INTER_AREA)
        np.testing.assert_array_equal(seen[index], expected)
        np.testing.assert_array_equal(written[index], expected)
        np.testing.assert_array_equal(ring[index], expected)
        np.testing.assert_array_equal(frames[index], frame)
    loader.close.assert_called_once()
    writer.release.assert_called_once()


def test_invalid_rotation_fails_before_opening_input(detector):
    with pytest.raises(ValueError, match='rotate_90'):
        detector.run(rotate_90='upside-down')
    detector.dataloader.next_clip.assert_not_called()


def parse_cli(cli, monkeypatch, argv):
    # Exercise the actual __main__ parser without launching capture or changing
    # the process-wide multiprocessing start method and exception hook.
    original = argparse.ArgumentParser.parse_args
    parsed = []
    class Parsed(Exception):
        pass
    def capture(parser, *args, **kwargs):
        parsed.append(original(parser, argv))
        raise Parsed()
    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', capture)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        with pytest.raises(Parsed):
            runpy.run_path(cli.__file__, run_name='__main__')
    finally:
        for handler in root.handlers[:]:
            if handler not in handlers:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)
    return parsed[0]


@pytest.mark.parametrize('direction', [None, 'cw', 'ccw'])
@pytest.mark.parametrize('multi', [False, True])
def test_cli_forwards_rotation_to_all_detectors(cli, monkeypatch, tmp_path, direction, multi):
    argv = ['a,b' if multi else 'input.mp4', str(tmp_path), '--test', '--fps', '2']
    if multi: argv += ['--multi-camera', '--no-composite']
    if direction: argv += ['--rotate-90', direction]
    args = parse_cli(cli, monkeypatch, argv)
    assert args.rotate_90 == direction
    monkeypatch.setattr(cli, 'LOCAL_DIR_PATH', str(tmp_path))
    monkeypatch.setattr(cli, 'setup_file_logging', Mock(return_value=tmp_path / 'test.log'))
    monkeypatch.setattr(cli.vl, 'VideoLoader', Mock())
    detectors = []
    def create(**kwargs):
        det = Mock()
        detectors.append(det)
        return det
    monkeypatch.setattr(cli.md, 'MotionDetector', create)
    def thread(*, target, args, **kwargs):
        result = Mock()
        result.start.side_effect = lambda: target(*args)
        return result
    monkeypatch.setattr(cli.threading, 'Thread', thread)
    if multi:
        # The real shutdown path raises when our finite mock detectors finish.
        with pytest.raises(RuntimeError, match='detector stopped unexpectedly'):
            cli.main(args)
    else:
        cli.main(args)
    assert len(detectors) == (2 if multi else 1)
    for det in detectors:
        det.run.assert_called_once()
        assert det.run.call_args.kwargs['rotate_90'] == direction


def test_cli_rejects_invalid_rotation(cli, monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as exc:
        parse_cli(cli, monkeypatch, ['input.mp4', str(tmp_path), '--rotate-90', '180'])
    assert exc.value.code == 2
