"""Configured dimensions must reach every consumer of the processed frames."""
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
from pysalmcount import clip_compositor as cc, motion_detect_stream as md, utils
from pysalmcount.dataloader import Item
from test_rotation import parse_cli


@pytest.mark.parametrize('width,height,rotation', [(1280,720,None),(704,480,None),(480,704,'cw'),(480,704,'ccw')])
def test_dimensions_reach_buffers_detector_and_continuous_writer(detector,monkeypatch,width,height,rotation):
    frame=np.arange(18,dtype=np.uint8).reshape(3,2,3)
    detector.dataloader.next_clip.return_value=Path('input.mp4')
    detector.dataloader.fps.return_value=2
    detector.dataloader.items.return_value=iter([Item(frame,1)])
    detector.save_cont_video=True
    seen=[]
    bg=Mock()
    bg.apply.side_effect=lambda value: (seen.append(value.copy()) or np.zeros(value.shape[:2],np.uint8))
    monkeypatch.setattr(md.cv2,'createBackgroundSubtractorMOG2',lambda **kw:bg)
    writer=Mock(); frames=[]
    writer.write.side_effect=lambda value:frames.append(value.copy())
    constructor=Mock(return_value=writer)
    monkeypatch.setattr(md.cv2,'VideoWriter',constructor)
    monkeypatch.setattr(utils,'ping_in_background',lambda *a:None)
    real_array=md.Array; buffers=[]
    def allocate(*args,**kwargs):
        raw=real_array(*args,**kwargs); buffers.append(raw); return raw
    monkeypatch.setattr(md,'Array',allocate)
    # Omit dimensions in the default case to verify backwards compatibility.
    kwargs={} if width==1280 else dict(frame_width=width,frame_height=height)
    detector.detect_motion=Mock(return_value=False)
    detector.run(fps=2,rotate_90=rotation,warmup_seconds=0,min_contour_area_ratio=.01,**kwargs)
    assert detector.detect_motion.call_args.kwargs['min_area']==int(width*height*.01)
    expected=cv2.resize(np.rot90(frame, -1 if rotation=='cw' else 1 if rotation=='ccw' else 0),
                       (width,height),interpolation=cv2.INTER_AREA)
    assert len(buffers[0])==4*width*height*3
    ring=np.ndarray((4,height,width,3),dtype=np.uint8,buffer=buffers[0])
    for actual in (seen[0],frames[0],ring[0]):
        np.testing.assert_array_equal(actual,expected)
    assert constructor.call_args.args[-1]==(width,height)


@pytest.mark.parametrize('name', ['frame_width','frame_height'])
@pytest.mark.parametrize('value', [0,-2,1,703,704.5,True])
def test_invalid_dimensions_fail_before_capture(detector,name,value):
    with pytest.raises(ValueError,match=name): detector.run(**{name:value})
    detector.dataloader.next_clip.assert_not_called()


@pytest.mark.parametrize('multi',[False,True])
def test_cli_forwards_dimensions_including_composite_jobs(cli,monkeypatch,tmp_path,multi):
    argv=['a,b' if multi else 'input.mp4',str(tmp_path),'--test','--fps','2',
          '--frame-width','480','--frame-height','704','--rotate-90','cw']
    if multi: argv+=['--multi-camera']
    args=parse_cli(cli,monkeypatch,argv)
    monkeypatch.setattr(cli,'LOCAL_DIR_PATH',str(tmp_path))
    monkeypatch.setattr(cli,'setup_file_logging',Mock())
    monkeypatch.setattr(cli.vl,'VideoLoader',Mock())
    detectors=[]
    def create(**kwargs):
        det=Mock(); detectors.append((det,kwargs)); return det
    monkeypatch.setattr(cli.md,'MotionDetector',create)
    def thread(*,target,args,**kwargs):
        t=Mock(); t.start.side_effect=lambda:target(*args); return t
    monkeypatch.setattr(cli.threading,'Thread',thread)
    recovered=Mock(return_value=[])
    monkeypatch.setattr(cli.cc,'find_stale_composite_jobs',recovered)
    monkeypatch.setattr(cli.cc,'CompositorWorker',Mock())
    import queue
    monkeypatch.setattr(cli.mp,'Queue',queue.Queue)
    if multi:
        with pytest.raises(RuntimeError,match='detector stopped unexpectedly'):cli.main(args)
        assert recovered.call_args.kwargs['frame_width']==480
        assert recovered.call_args.kwargs['frame_height']==704
        coord=detectors[0][1]['coordinator']
        info=coord.enter_event('cam1')
        coord.report_part_finished('cam1',info,{'path':'one.mp4'})
        job=coord.report_part_finished('cam2',info,{'path':'two.mp4'})
        assert (job.frame_width,job.frame_height)==(480,704)
    else: cli.main(args)
    assert len(detectors)==(2 if multi else 1)
    for det,_ in detectors:
        assert det.run.call_args.kwargs['frame_width']==480
        assert det.run.call_args.kwargs['frame_height']==704


@pytest.mark.parametrize('flag,value',[('--frame-width','0'),('--frame-height','703')])
def test_live_cli_rejects_invalid_sizes_without_capture(cli,flag,value,tmp_path):
    env=dict(os.environ,PYTHONPATH=str(Path(md.__file__).resolve().parents[1]))
    result=subprocess.run([sys.executable,cli.__file__,'missing.mp4',str(tmp_path),flag,value],
                          env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==2 and 'positive even integers' in result.stderr


@pytest.fixture
def batch():
    path=Path(md.__file__).resolve().parents[2]/'tools/batch_motion_h264.py'
    spec=importlib.util.spec_from_file_location('batch_dimensions',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.mark.parametrize('width,height',[(704,480),(480,704)])
def test_batch_settings_include_dimensions_for_resume(batch,monkeypatch,tmp_path,width,height):
    root=tmp_path/'input'; source=root/'20260720/1400/CH01.h264'
    source.parent.mkdir(parents=True);source.write_bytes(b'input')
    process=Mock(return_value='processed');monkeypatch.setattr(batch,'process_source',process)
    monkeypatch.setattr(batch.shutil,'which',lambda name:name)
    args=[str(root),str(tmp_path/'out'),'--source-fps','30','--device-id','device',
          '--frame-width',str(width),'--frame-height',str(height)]
    assert batch.main(args)==0
    cfg=process.call_args.args[3]
    assert cfg['frame_width']==width and cfg['frame_height']==height
    ident=batch.source_identity(source,root)
    assert batch.signature(ident,cfg)!=batch.signature(ident,dict(cfg,frame_width=1280))


@pytest.mark.parametrize('flag,value',[('--frame-width','0'),('--frame-height','703')])
def test_batch_rejects_invalid_dimensions(batch,flag,value):
    with pytest.raises(SystemExit):
        batch.parse_args(['in','out','--source-fps','30','--device-id','device',flag,value])


def test_recovered_composites_preserve_configured_dimensions(tmp_path):
    parts=tmp_path/'parts';parts.mkdir()
    (parts/'top_20260720_140000_Eabcdef_p001_M.mp4').write_bytes(b'source')
    jobs=cc.find_stale_composite_jobs(parts,['top','bottom'],tmp_path/'out','device',10,False,
        0,now=10**12,frame_width=480,frame_height=704)
    assert len(jobs)==1 and (jobs[0].frame_width,jobs[0].frame_height)==(480,704)
    command=cc.build_ffmpeg_cmd(jobs[0],tmp_path/'out.mp4',cc.EndAlignment([4,None],[0,0],4))
    assert 'color=c=black:s=480x704:r=10' in command
    assert 'scale=480:704' in command[command.index('-filter_complex')+1]


@pytest.mark.smoke
@pytest.mark.parametrize('width,height',[(704,480),(480,704)])
def test_real_composite_has_configured_row_dimensions(tmp_path,width,height):
    import shutil
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):pytest.skip('FFmpeg required')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=red:s={width}x{height}:r=10',
        '-frames:v','3','-c:v','libx264','-threads','1',str(source)],check=True,timeout=20)
    job=cc.CompositeJob('event_abcdef',1,datetime.now(timezone.utc),
        [cc.CompositeSource('top',source),cc.CompositeSource('missing',None)],
        tmp_path/'motion_vids','device',10,False,frame_width=width,frame_height=height)
    output=cc.run_composite(job)
    meta=utils.get_video_metadata(output)
    assert (meta.width,meta.height,meta.nb_frames)==(width,2*height,3)
    capture=cv2.VideoCapture(str(output))
    try:
        ok,frame=capture.read();assert ok
        assert frame[:height,:,2].mean()>200
        assert frame[height:,:,:].mean()<5
    finally:capture.release()
