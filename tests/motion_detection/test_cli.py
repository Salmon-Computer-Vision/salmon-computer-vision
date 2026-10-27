from types import SimpleNamespace
from unittest.mock import Mock
import queue
import threading
import pytest

@pytest.mark.parametrize('names,expected', [(None, ['cam1','cam2']), (' top , bottom ', ['top','bottom'])])
def test_multi_camera_parse(cli, names, expected):
    urls, cameras = cli._parse_multi_camera_args(SimpleNamespace(input=' rtsp://a , rtsp://b ', cam_names=names))
    assert urls == ['rtsp://a', 'rtsp://b'] and cameras == expected

@pytest.mark.parametrize('urls,names', [('rtsp://a',None), ('a,b','top'), ('a,b','top,top'), ('a,b','top,'), ('a,b','../top,bottom')])
def test_invalid_multi_camera_cli(cli, urls, names):
    with pytest.raises(ValueError): cli._parse_multi_camera_args(SimpleNamespace(input=urls, cam_names=names))

def test_device_name_and_url_file(cli, tmp_path):
    assert cli.get_orgid_and_site_name('HIRMD-koeye-jetson-0') == ('HIRMD', 'koeye', 'jetson-0')
    path = tmp_path / 'url.txt'; path.write_text(' rtsp://example.invalid/live \nignored\n')
    assert cli.read_rtsp_url(path) == 'rtsp://example.invalid/live'

@pytest.mark.parametrize('gst,h265,fragment', [(False,False,None),(True,False,'rtph264depay'),(True,True,'decodebin')])
def test_input_pipeline(cli, gst, h265, fragment):
    url = 'rtsp://example.invalid/live'
    result = cli._build_input_str(url, gst, h265)
    if fragment is None: assert result == url
    else: assert fragment in result and url in result and 'appsink' in result

@pytest.mark.parametrize('error', [None, ValueError('camera failed')])
def test_camera_termination_stops_peers_and_reraises(cli, monkeypatch, error):
    q = queue.Queue(); q.put(('top', error))
    stop = threading.Event(); threads = [Mock(), Mock()]
    cleanup = Mock(); monkeypatch.setattr(cli, '_stop_compositor', cleanup)
    with pytest.raises(RuntimeError if error is None else ValueError) as caught:
        cli._shutdown_on_camera_termination(q, stop, threads)
    if error is not None: assert caught.value is error
    assert stop.is_set()
    for thread in threads: thread.join.assert_called_once()
    cleanup.assert_called_once()

def test_compositor_shutdown_flushes_before_sentinel(cli):
    coord = Mock(); coord.reap_stale_parts.return_value = [SimpleNamespace(event_id='e', part_number=1)]
    worker = Mock(); worker.is_alive.side_effect = [True, False]
    q = queue.Queue()
    cli._stop_compositor(coord, q, worker)
    coord.reap_stale_parts.assert_called_once_with(force=True)
    assert q.get_nowait().event_id == 'e'
    assert q.get_nowait() is None
    worker.terminate.assert_not_called()
