from unittest.mock import Mock
from pathlib import Path
import pytest
import requests
from pysalmcount import utils

@pytest.fixture
def stream():
    return dict(codec_type='video', codec_name='h264', duration='1.5', nb_frames='15',
        width='1280', height='720', start_time='0', avg_frame_rate='10/1', r_frame_rate='10/1')

def test_parse_metadata(stream):
    result = utils.parse_ffmpeg_video_stream_probe(stream)
    assert result == utils.VideoMetadata(1.5, 'h264', 15, 1280, 720, 0.0, '10/1', '10/1')

@pytest.mark.parametrize('field', ['duration', 'nb_frames', 'width', 'height', 'start_time'])
def test_invalid_metadata_returns_none(stream, field):
    stream[field] = 'N/A'
    assert utils.parse_ffmpeg_video_stream_probe(stream) is None

def test_missing_metadata_returns_none():
    assert utils.parse_ffmpeg_video_stream_probe({}) is None

def test_probe_selects_video_not_audio(stream, monkeypatch):
    probe = Mock(return_value={'streams': [{'codec_type': 'audio'}, stream]})
    monkeypatch.setattr(utils.ffmpeg, 'probe', probe)
    assert utils.get_video_metadata(Path('clip.mp4')).nb_frames == 15
    probe.assert_called_once_with(Path('clip.mp4'))

def test_no_video_stream(monkeypatch):
    monkeypatch.setattr(utils.ffmpeg, 'probe', lambda p: {'streams': [{'codec_type': 'audio'}]})
    assert utils.get_video_metadata(Path('audio.mp4')) is None

def test_probe_error(monkeypatch):
    monkeypatch.setattr(utils.ffmpeg, 'probe', Mock(side_effect=utils.ffmpeg.Error('ffprobe', b'', b'bad file')))
    assert utils.get_video_metadata(Path('bad.mp4')) is None

@pytest.mark.parametrize('frame,expected', [(0, True), (299, False), (300, True), (301, False), (600, True)])
def test_healthcheck_cadence(frame, expected):
    assert utils.is_check_time(frame, 10) is expected

@pytest.mark.parametrize('failure', [None, requests.Timeout('timeout'), requests.HTTPError('503')])
def test_ping_timeout_and_errors(monkeypatch, failure):
    response = Mock()
    response.raise_for_status.side_effect = failure
    get = Mock(return_value=response)
    monkeypatch.setattr(utils.requests, 'get', get)
    utils.send_ping('https://example.invalid/health')
    get.assert_called_once_with('https://example.invalid/health', timeout=10)
    response.raise_for_status.assert_called_once()

def test_background_ping_thread_completes(monkeypatch):
    send = Mock()
    monkeypatch.setattr(utils, 'send_ping', send)
    thread = utils.ping_in_background('test-url')
    thread.join(timeout=2)
    assert thread.daemon and not thread.is_alive()
    send.assert_called_once_with('test-url')
