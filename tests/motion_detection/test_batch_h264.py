import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import pytest
from pysalmcount import motion_detect_stream as md

@pytest.fixture
def batch():
    script = Path(md.__file__).resolve().parents[2] / 'tools/batch_motion_h264.py'
    spec = importlib.util.spec_from_file_location('batch_h264_under_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_source(root, rel='20260720/1400/CH01.h264'):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'input')
    return path


def test_discover_nested_dates_and_ignore_system_folders(batch, tmp_path):
    top = make_source(tmp_path)
    nested = make_source(tmp_path, '20260825/20260719/2359/CH01.h264')
    make_source(tmp_path, '$RECYCLE.BIN/20260101/0000/CH01.h264')
    make_source(tmp_path, 'System Volume Information/20260101/0000/CH01.h264')
    (top.parent/'CH01.index').write_text('index')
    assert batch.discover(tmp_path) == [nested, top]
    assert batch.folder_timestamp(nested).isoformat() == '2026-07-19T23:59:00'


@pytest.mark.parametrize('relative', ['20260230/1400/a.h264','20260720/2460/a.h264','202607/1400/a.h264'])
def test_invalid_timestamp(batch, relative):
    with pytest.raises(ValueError): batch.folder_timestamp(Path(relative))


def test_symlink_is_not_followed(batch, tmp_path):
    root = tmp_path/'input'; root.mkdir()
    other = make_source(tmp_path/'other')
    (root/'20260720').symlink_to(other.parent.parent, target_is_directory=True)
    assert batch.discover(root) == []


def test_dry_run_is_read_only_and_uses_folder_time(batch, tmp_path, capsys):
    root = tmp_path/'input'; source = make_source(root)
    out = tmp_path/'out'
    assert batch.main([str(root),str(out),'--source-fps','10','--device-id','ORG-site-pi-0','--dry-run']) == 0
    assert '2026-07-20T14:00:00' in capsys.readouterr().out
    assert not out.exists() and source.read_bytes() == b'input'


def test_required_source_fps(batch, tmp_path):
    with pytest.raises(SystemExit):
        batch.parse_args([str(tmp_path),str(tmp_path/'out'),'--device-id','device'])


@pytest.mark.parametrize('fps', ['0', '-1', 'nan', '29.97'])
def test_bad_or_unsupported_fps_rejected(batch, fps):
    with pytest.raises((SystemExit, ValueError)):
        batch.parse_args(['in','out','--device-id','device','--source-fps',fps])


def test_remux_is_stream_copy_and_input_rate_precedes_input(batch):
    command = batch.remux_command(Path('source file.h264'),Path('output file.mp4'),10)
    assert command[command.index('-r')+1] == '10'
    assert command.index('-r') < command.index('-i')
    assert command[command.index('-c:v')+1] == 'copy'
    assert 'source file.h264' in command and command[-1] == 'output file.mp4'


@pytest.fixture
def settings():
    return dict(source_fps=2,device_id='ORG-site-pi-0',rotate_90=None,encoder='cpu-h264',
                algo='MOG2',min_contour_area=5000,motion_trigger_seconds=.4,
                warmup_seconds=1,bitrate=3000,recording_timezone='unspecified')


def test_publish_and_resume_do_not_rerun_completed_source(batch, tmp_path, monkeypatch, settings):
    root=tmp_path/'input'; source=make_source(root)
    out=tmp_path/'out'; out.mkdir()
    calls=[]
    def run(command, log, timeout):
        calls.append(command)
        if command[0]=='ffmpeg': Path(command[-1]).write_bytes(b'remux')
        else:
            job=json.loads(Path(command[-1]).read_text())
            stage=Path(job['output'])
            (stage/'worker-result.json').write_text('{"motion_clips":0}')
    monkeypatch.setattr(batch,'run_checked',run)
    assert batch.process_source(source,root,out,settings,30)=='processed'
    final=out/'results/20260720/1400/CH01'
    manifest=json.loads((final/'complete.json').read_text())
    assert manifest['folder_start']=='2026-07-20T14:00:00'
    assert manifest['source']['relative_path']=='20260720/1400/CH01.h264'
    assert batch.process_source(source,root,out,settings,30)=='skipped'
    assert len(calls)==2
    assert list((out/'.work').iterdir())==[]
    assert source.read_bytes()==b'input'
    changed=dict(settings,rotate_90='cw')
    with pytest.raises(RuntimeError, match='Cannot resume'):
        batch.process_source(source,root,out,changed,30)
    source.write_bytes(b'changed source')
    with pytest.raises(RuntimeError, match='Cannot resume'):
        batch.process_source(source,root,out,settings,30)


def test_failed_job_not_marked_complete(batch,tmp_path,monkeypatch,settings):
    root=tmp_path/'input'; source=make_source(root)
    out=tmp_path/'out'; out.mkdir()
    monkeypatch.setattr(batch,'run_checked',Mock(side_effect=RuntimeError('bad encoder')))
    with pytest.raises(RuntimeError): batch.process_source(source,root,out,settings,30)
    assert not (out/'results/20260720/1400/CH01').exists()
    assert list((out/'.work').iterdir())==[]
    assert list((out/'logs').rglob('*.log'))
    assert source.read_bytes()==b'input'


def test_resume_requires_output_inventory(batch,tmp_path):
    final=tmp_path/'final'; final.mkdir()
    (final/'complete.json').write_text(json.dumps({'schema':1,'signature':'s','outputs':[{'path':'missing.mp4','size':5}]}))
    with pytest.raises(RuntimeError,match='Cannot resume'): batch.is_complete(final,'s')


def test_output_lock_prevents_concurrent_batches(batch,tmp_path):
    with batch.output_lock(tmp_path):
        with pytest.raises(RuntimeError,match='Another batch'):
            with batch.output_lock(tmp_path): pass


def test_command_timeout_is_failure_and_child_is_reaped(batch,tmp_path):
    with (tmp_path/'log').open('w') as log:
        with pytest.raises(subprocess.TimeoutExpired):
            batch.run_checked([sys.executable,'-c','import time;time.sleep(20)'],log,.1)


@pytest.mark.smoke
def test_real_raw_h264_batch_no_motion_and_resume(batch,tmp_path,settings):
    import shutil
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): pytest.skip('FFmpeg required')
    root=tmp_path/'input'; path=make_source(root,'20260720/2359/CH01.h264')
    # Static black, two seconds warmup: no output encoder needed on this host.
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:s=128x72:r=2',
        '-frames:v','4','-c:v','libx264','-threads','1','-bf','0','-f','h264',str(path)],check=True,timeout=20)
    out=tmp_path/'out'
    command=[sys.executable,str(batch.SCRIPT),str(root),str(out),'--source-fps','2',
             '--device-id','test-device','--warmup-seconds','2','--job-timeout','30']
    first=subprocess.run(command,capture_output=True,text=True,timeout=45)
    logs='\n'.join(p.read_text() for p in out.glob('logs/**/*.log'))
    assert first.returncode==0,first.stderr+'\n'+logs
    final=out/'results/20260720/2359/CH01'
    manifest=json.loads((final/'complete.json').read_text())
    assert manifest['worker']['input_frames']==4
    assert manifest['worker']['processed_frames']==4
    assert manifest['worker']['motion_clips']==0
    assert manifest['folder_start']=='2026-07-20T23:59:00'
    second=subprocess.run(command,capture_output=True,text=True,timeout=10)
    assert second.returncode==0 and 'SKIP completed' in second.stderr
    assert len(list(out.glob('logs/**/*.log')))==1

@pytest.mark.smoke
@pytest.mark.parametrize('bframes', [0, 2])
def test_remux_preserves_frame_count_and_original_rate(batch,tmp_path,bframes):
    import shutil
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): pytest.skip('FFmpeg required')
    raw=tmp_path/'raw.h264'; output=tmp_path/'prepared.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=128x72:r=10',
        '-frames:v','30','-c:v','libx264','-threads','1','-bf',str(bframes),'-f','h264',str(raw)],check=True,timeout=20)
    with (tmp_path/'remux.log').open('w') as log:
        batch.run_checked(batch.remux_command(raw,output,10),log,20)
    data=batch.probe(output)
    assert int(data['nb_frames'])==30
    assert data['avg_frame_rate']=='10/1'
    assert float(data['duration'])==pytest.approx(3.0,abs=.01)


def test_worker_preserves_midnight_crossing_and_provenance(batch,tmp_path,monkeypatch,settings):
    import multiprocessing as mp
    from pysalmcount import videoloader as vl, utils
    monkeypatch.setattr(utils, 'ping_in_background', utils.ping_in_background)
    monkeypatch.setattr(mp,'set_start_method',lambda *a,**k:None)
    class Loader:
        def __init__(self,*a,**k):
            assert k['target_fps'] is None
        def items(self):
            yield from range(400)
    monkeypatch.setattr(vl,'VideoLoader',Loader)
    calls=[]
    class Detector:
        def __init__(self,loader,out,**kwargs):
            self.loader,self.out=loader,out
            self.status_q,self.result_q=Mock(),Mock()
            assert kwargs['is_video'] and not kwargs['save_cont_video']
            assert kwargs['save_prefix']=='device_CH01'
        def run(self,**kwargs):
            calls.append(kwargs)
            list(self.loader.items())
            (self.out/'motion_vids').mkdir()
            (self.out/'motion_vids_metadata').mkdir()
            name='device_CH01_20260721_000100_M'
            (self.out/'motion_vids'/f'{name}.mp4').write_bytes(b'clip')
            (self.out/'motion_vids_metadata'/f'{name}.json').write_text('{"nb_frames":60}')
            return {'input_20260720_235900.mp4':[(240,300)]}
        def _raise_if_video_saver_failed(self): pass
    monkeypatch.setattr(md,'MotionDetector',Detector)
    monkeypatch.setattr(batch,'probe',lambda p:dict(nb_frames='400' if p.name.startswith('input_') else '60',avg_frame_rate='2/1'))
    out=tmp_path/'result'; out.mkdir()
    job=dict(input=str(tmp_path/'input_20260720_235900.mp4'),output=str(out),
        settings=dict(settings,rotate_90='cw',frame_width=480,frame_height=704),source={'relative_path':'20260720/2359/CH01.h264'},
        folder_start='2026-07-20T23:59:00',prefix='device_CH01')
    path=tmp_path/'job.json'; path.write_text(json.dumps(job))
    batch.worker(path)
    assert calls[0]['fps']==2 and calls[0]['rotate_90']=='cw'
    assert (calls[0]['frame_width'],calls[0]['frame_height'])==(480,704)
    data=json.loads(next((out/'motion_vids_metadata').glob('*.json')).read_text())
    assert data['archive_source']['motion_trigger_time']=='2026-07-21T00:01:00'
    assert data['archive_source']['folder_start']=='2026-07-20T23:59:00'
    assert data['archive_source']['motion_trigger_frame']==240
    assert (data['archive_source']['frame_width'],data['archive_source']['frame_height'])==(480,704)
    assert json.loads((out/'worker-result.json').read_text())['processed_frames']==400


def test_same_drive_output_subdirectory_is_supported(batch,tmp_path,capsys):
    make_source(tmp_path)
    output=tmp_path/'motion-results'
    # Previously created output directories must never be rediscovered.
    make_source(output,'results/20260720/1400/CH01.h264')
    assert batch.main([str(tmp_path),str(output),'--source-fps','10','--device-id','device','--dry-run'])==0
    assert '1 input(s)' in capsys.readouterr().out
