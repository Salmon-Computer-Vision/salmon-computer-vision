"""Hardware-free tests; integration tests use PyArrow when installed."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from object_detection.tracking_eval import inference as i


class Array:
    def __init__(self, values):
        self.values = np.array(values)
    def cpu(self):
        return self
    def numpy(self):
        return self.values


class Boxes:
    def __init__(self, ids, xyxy=None, cls=None, conf=None, *, n_without_ids=0):
        if ids is None:
            self.id = None
            self.n = n_without_ids
        else:
            self.id = Array(ids)
            self.n = len(ids)
        self.xyxy = Array(xyxy if xyxy is not None else [])
        self.cls = Array(cls if cls is not None else [])
        self.conf = Array(conf if conf is not None else [])
    def __len__(self):
        return self.n


def task(stem="A", *, split="val", site="koeye", frames=3, path=None):
    return i.Task(split, site, stem, Path(path or f"/tmp/{stem}.mp4"), "downloaded", frames, 8, 8)


def pred(boxes):
    return SimpleNamespace(boxes=boxes)


def save_csv(path, fields, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_schema_columns_contract():
    assert i.PREDICTION_COLUMNS == (
        "split", "site", "video_stem", "frame_idx", "mot_frame", "track_id",
        "class_id", "confidence", "x_px", "y_px", "width_px", "height_px",
    )


def test_rows_valid_index_geometry_and_class():
    b = Boxes([17], [[1.5, 2.5, 6.5, 7.5]], [4], [0.91])
    rows, missing = i.rows_for_result(pred(b), task=task(), frame_idx=3, width=8, height=8)
    assert missing == 0
    assert rows == [{"split":"val", "site":"koeye", "video_stem":"A",
                     "frame_idx":3, "mot_frame":4, "track_id":17,
                     "class_id":4, "confidence":pytest.approx(.91),
                     "x_px":1.5, "y_px":2.5, "width_px":5., "height_px":5.}]


def test_box_clipped_to_image():
    b = Boxes([1], [[-2, -4, 4, 10]], [0], [.9])
    rows, _ = i.rows_for_result(pred(b), task=task(), frame_idx=0, width=8, height=8)
    assert rows[0]["x_px"] == rows[0]["y_px"] == 0
    assert rows[0]["width_px"] == 4
    assert rows[0]["height_px"] == 8


@pytest.mark.parametrize("box", [[1,1,1,5], [0,0,-1,3], [float('nan'),0,3,4], [20,1,30,5]])
def test_invalid_box_rejected(box):
    with pytest.raises(ValueError):
        i.rows_for_result(pred(Boxes([1], [box], [1], [.5])), task=task(), frame_idx=0, width=8, height=8)


@pytest.mark.parametrize("ids,classes,scores", [([0],[1],[.5]), ([-1],[1],[.5]),
                                                 ([1],[-1],[.5]), ([1],[0],[1.5]),
                                                 ([1.4],[1],[.5])])
def test_invalid_id_class_conf_rejected(ids, classes, scores):
    with pytest.raises(ValueError):
        i.rows_for_result(pred(Boxes(ids, [[1,1,2,2]], classes, scores)), task=task(), frame_idx=0, width=8, height=8)


def test_duplicate_track_id_in_frame_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        i.rows_for_result(pred(Boxes([1,1], [[1,1,2,2],[2,2,3,3]], [1,1], [.9,.9])), task=task(), frame_idx=0, width=8, height=8)


def test_no_tracks_distinguishes_untracked_and_empty():
    a, missing = i.rows_for_result(pred(Boxes(None, n_without_ids=3)), task=task(), frame_idx=0, width=8, height=8)
    assert a == [] and missing == 3
    a, missing = i.rows_for_result(pred(Boxes([])), task=task(), frame_idx=1, width=8, height=8)
    assert a == [] and missing == 0


def test_read_tasks_rejects_split_mismatch_and_path_mismatch(tmp_path):
    evalp, statusp, seqp = (tmp_path / f for f in ('eval.csv','status.csv','sequences.csv'))
    video = tmp_path / 'A.mp4'
    save_csv(evalp, ['split','site','video_stem','local_video_path'],
             [{'split':'val','site':'koeye','video_stem':'A','local_video_path':str(video)}])
    save_csv(statusp, ['split','video_stem','status','local_video_path'],
             [{'split':'test','video_stem':'A','status':'downloaded','local_video_path':str(video)}])
    save_csv(seqp, ['split','site','video_stem','nb_frames','width','height'],
             [{'split':'val','site':'koeye','video_stem':'A','nb_frames':3,'width':8,'height':8}])
    with pytest.raises(ValueError, match="split mismatch"):
        i.read_tasks(evalp, statusp, seqp, 'val')
    save_csv(statusp, ['split','video_stem','status','local_video_path'],
             [{'split':'val','video_stem':'A','status':'downloaded','local_video_path':str(video)+'x'}])
    with pytest.raises(ValueError, match="Different local video paths"):
        i.read_tasks(evalp, statusp, seqp, 'val')


def test_read_tasks_duplicate_and_missing(tmp_path):
    evalp, statusp, seqp = (tmp_path / f for f in ('eval.csv','status.csv','seq.csv'))
    row = {'split':'val','video_stem':'A','local_video_path':'A.mp4'}
    save_csv(evalp, list(row), [row,row])
    save_csv(statusp, [*row,'status'], [{**row,'status':'existing'}])
    save_csv(seqp, ['split','video_stem','nb_frames','width','height'],
             [{'split':'val','video_stem':'A','nb_frames':3,'width':8,'height':8}])
    with pytest.raises(ValueError, match="duplicate"):
        i.read_tasks(evalp,statusp,seqp,'val')
    save_csv(evalp, list(row), [row, {**row,'video_stem':'B'}])
    with pytest.raises(ValueError, match="different video sets"):
        i.read_tasks(evalp,statusp,seqp,'val')


class Capture:
    def __init__(self, frames, *, frame_count=None, opened=True):
        self.frames = frames
        self.pos = 0
        self.frame_count = len(frames) if frame_count is None else frame_count
        self.opened = opened
        self.released = False
    def isOpened(self):
        return self.opened
    def get(self, prop):
        return {5:10,7:self.frame_count}.get(prop,0)
    def read(self):
        if self.pos == len(self.frames):
            return False, None
        f = self.frames[self.pos]
        self.pos += 1
        return True, f
    def release(self):
        self.released = True


class CV2:
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_COUNT = 7
    __version__ = 'mock-1'
    def __init__(self, captures):
        self.captures = captures
    def VideoCapture(self, path):
        return self.captures[path]


class Tracker:
    def __init__(self):
        self.current = 0
        self.resets = 0
    def reset(self):
        self.current = 0
        self.resets += 1


class Model:
    def __init__(self):
        self.predictor = None
        self.calls = []
    def track(self, source, **kwargs):
        assert kwargs['persist'] is True
        assert kwargs['save'] is False
        self.calls.append(kwargs)
        if self.predictor is None:
            self.predictor = SimpleNamespace(trackers=[Tracker()], vid_path=['old'])
        self.predictor.trackers[0].current += 1
        tid = self.predictor.trackers[0].current
        return [pred(Boxes([tid], [[1,1,3,4]], [2], [.75]))]


def frames(n):
    return [np.zeros((8,8,3),dtype=np.uint8) for _ in range(n)]


def test_infer_video_frame_indexes_and_reset_between_videos():
    a,b=task('A',frames=3),task('B',frames=2)
    cv=CV2({str(a.path):Capture(frames(3)),str(b.path):Capture(frames(2))})
    model=Model()
    setting=i.Settings('botsort.yaml', .05,.7,640,'0')
    rows_a,stats_a=i.infer_video(a, model, setting, cv.VideoCapture, cv)
    rows_b,stats_b=i.infer_video(b, model, setting, cv.VideoCapture, cv)
    assert [r['frame_idx'] for r in rows_a] == [0,1,2]
    assert [r['mot_frame'] for r in rows_a] == [1,2,3]
    assert [r['track_id'] for r in rows_a] == [1,2,3]
    assert [r['track_id'] for r in rows_b] == [1,2]
    assert model.predictor.trackers[0].resets == 1
    assert stats_a['frames_decoded'] == 3 and stats_b['frames_decoded'] == 2
    assert cv.captures[str(a.path)].released and cv.captures[str(b.path)].released


def test_infer_video_failed_decode_releases_capture():
    t=task('A',frames=3)
    cap=Capture([],opened=False)
    cv=CV2({str(t.path):cap})
    with pytest.raises(OSError,match='open'):
        i.infer_video(t, Model(), i.Settings('botsort.yaml',.1,.7,640,'0'),cv.VideoCapture,cv)
    assert cap.released


def test_frame_count_and_resolution_mismatch_reported():
    t=task('A',frames=100)
    cv=CV2({str(t.path):Capture(frames(3),frame_count=100)})
    with pytest.raises(ValueError,match='expected 100'):
        i.infer_video(t, Model(),i.Settings('botsort.yaml',.1,.7,640,'0'),cv.VideoCapture,cv)
    t2=task('A',frames=1)
    cv=CV2({str(t2.path):Capture([np.zeros((4,4,3),dtype=np.uint8)])})
    with pytest.raises(ValueError,match='GT resolution'):
        i.infer_video(t2, Model(),i.Settings('botsort.yaml',.1,.7,640,'0'),cv.VideoCapture,cv)


def test_tracker_reset_failure_is_not_ignored():
    obj=SimpleNamespace(predictor=SimpleNamespace(trackers=[object()],vid_path=['x']))
    with pytest.raises(RuntimeError,match='reset'):
        i.reset_trackers(obj)


def test_cache_fingerprint_video_change(tmp_path):
    path=tmp_path/'A.mp4'
    path.write_bytes(b'abc')
    t=task('A',path=path)
    key1=i.video_fingerprint(t,'run-signature')
    path.write_bytes(b'abcd')
    assert i.video_fingerprint(t,'run-signature') != key1
    assert i.video_fingerprint(t,'another-run-signature') != key1


def test_settings_validation():
    i.Settings('botsort.yaml',.05,.7,640,'0').validate()
    for settings in [i.Settings('',.05,.7,640,'0'),i.Settings('bt',0,.7,640,'0'),
                     i.Settings('bt',.05,1.5,640,'0'),i.Settings('bt',.05,.7,-1,'0')]:
        with pytest.raises(ValueError):settings.validate()


# These tests validate genuine Parquet IO and are automatically activated once
# the project's documented `pyarrow` dependency is installed.
def test_parquet_schema_and_empty_shard(tmp_path):
    pa=pytest.importorskip('pyarrow')
    import pyarrow.parquet as pq
    p=tmp_path/'empty.parquet'
    i._atomic_parquet([],p)
    assert pq.ParquetFile(p).metadata.num_rows == 0
    assert pq.read_schema(p).equals(i.prediction_schema())
    p2=tmp_path/'one.parquet'
    row, _=i.rows_for_result(pred(Boxes([1],[[1,2,3,4]],[2],[.8])),task=task(),frame_idx=0,width=8,height=8)
    i._atomic_parquet(row,p2)
    assert pq.read_table(p2)['mot_frame'].to_pylist()==[1]


def test_infer_split_resume_and_failures(tmp_path):
    pa=pytest.importorskip('pyarrow')
    import pyarrow.parquet as pq
    a,b,c=[task(name,frames=2,path=tmp_path/f'{name}.mp4') for name in ('A','B','C')]
    c=i.Task(c.split,c.site,c.video_stem,c.path,'archived',c.gt_nb_frames,c.gt_width,c.gt_height)
    a.path.write_bytes(b'a');b.path.write_bytes(b'b')
    cv=CV2({str(a.path):Capture(frames(2)),str(b.path):Capture(frames(2))})
    model=Model(); calls=[]
    def loader(path):
        calls.append(path)
        return model
    args=dict(tasks=[a,b,c],settings=i.Settings('botsort.yaml',.05,.7,640,'0'),
              model_path=tmp_path/'best.pt',cache_dir=tmp_path/'shards',
              predictions_path=tmp_path/'pred.parquet',status_path=tmp_path/'status.csv',
              summary_path=tmp_path/'summary.json',backend_factory=loader,
              cv2_module=cv,ultralytics_version='test-ver')
    args['model_path'].write_bytes(b'model')
    summary=i.infer_split(**args)
    assert summary['videos_ok']==2 and summary['videos_unavailable']==1
    assert summary['predictions_written']==4
    assert len(calls)==1
    assert pq.read_table(args['predictions_path']).num_rows==4
    assert json.loads(args['summary_path'].read_text())['videos_ok']==2
    assert [x['reused_cache'] for x in list(csv.DictReader(args['status_path'].open()))]==['False','False','False']
    # Called again with the same frame source, everything should be cached.
    summary=i.infer_split(**args)
    assert summary['videos_resumed']==2 and len(calls)==1
    assert [x['reused_cache'] for x in list(csv.DictReader(args['status_path'].open()))]==['True','True','False']
    # If one video is replaced, only it should be processed again.
    b.path.write_bytes(b'changed')
    cv.captures[str(b.path)]=Capture(frames(2))
    summary=i.infer_split(**args)
    assert summary['videos_resumed']==1
    assert len(calls)==2


def test_infer_split_failure_writes_status_and_resumable_success(tmp_path):
    pytest.importorskip('pyarrow')
    a=task('A',frames=2,path=tmp_path/'A.mp4')
    b=task('B',frames=2,path=tmp_path/'B.mp4')
    a.path.write_bytes(b'a'); b.path.write_bytes(b'b')
    cv=CV2({str(a.path):Capture(frames(2)),str(b.path):Capture([],opened=False)})
    model=Model()
    args=dict(tasks=[a,b],settings=i.Settings('botsort.yaml',.05,.7,640,'0'),
              model_path=tmp_path/'m.pt',cache_dir=tmp_path/'shards',
              predictions_path=tmp_path/'p.parquet',status_path=tmp_path/'status.csv',
              summary_path=tmp_path/'summary.json',backend_factory=lambda _:model,
              cv2_module=cv,ultralytics_version='test')
    args['model_path'].write_bytes(b'model')
    with pytest.raises(RuntimeError,match='incomplete'):
        i.infer_split(**args)
    statuses=list(csv.DictReader(args['status_path'].open()))
    assert [x['status'] for x in statuses]==['ok','error']
    assert json.loads(args['summary_path'].read_text())['videos_failed']==1
    cv.captures[str(b.path)]=Capture(frames(2))
    summary=i.infer_split(**args)
    assert summary['videos_resumed']==1 and summary['videos_ok']==2


def test_infer_split_orchestration_without_pyarrow(tmp_path, monkeypatch):
    """Test resumability, exclusions and failure with mocked Parquet persistence."""
    a=task('A',frames=2,path=tmp_path/'A.mp4')
    b=task('B',frames=2,path=tmp_path/'B.mp4')
    c=task('C',frames=2,path=tmp_path/'C.mp4')
    c=i.Task(c.split,c.site,c.video_stem,c.path,'archived',c.gt_nb_frames,c.gt_width,c.gt_height)
    a.path.write_bytes(b'a');b.path.write_bytes(b'b')
    cv=CV2({str(a.path):Capture(frames(2)),str(b.path):Capture(frames(2))})
    calls=[]
    def loader(_):
        calls.append('loaded')
        return Model()
    # Emulate stable Parquet on disk for high-level flow while PyArrow tests
    # exercise real Parquet serialization in environments with it installed.
    def write(rows,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(rows))
    def count(path):
        return len(json.loads(path.read_text()))
    def merge(tasks,statuses,cache_dir,path):
        combined=[]
        for t,s in zip(tasks,statuses):
            if s['status']=='ok':
                combined+=json.loads((cache_dir/f'{t.video_stem}.parquet').read_text())
        path.write_text(json.dumps(combined))
    monkeypatch.setattr(i,'_atomic_parquet',write)
    monkeypatch.setattr(i,'_parquet_rows',count)
    monkeypatch.setattr(i,'_merge_parquets',merge)
    monkeypatch.setattr(i,'_arrow',lambda: (None,SimpleNamespace(ParquetFile=lambda _: SimpleNamespace(schema_arrow=SimpleNamespace(equals=lambda _:True)))))
    monkeypatch.setattr(i,'prediction_schema',lambda:None)
    args=dict(tasks=[a,b,c], settings=i.Settings('botsort.yaml',.05,.7,640,'0'),
              model_path=tmp_path/'model.pt', cache_dir=tmp_path/'cache',
              predictions_path=tmp_path/'pred.json', status_path=tmp_path/'status.csv',
              summary_path=tmp_path/'summary.json',backend_factory=loader,
              cv2_module=cv,ultralytics_version='test')
    args['model_path'].write_bytes(b'weights')
    s=i.infer_split(**args)
    assert (s['videos_ok'],s['videos_unavailable'],s['predictions_written'])==(2,1,4)
    assert len(calls)==1
    assert json.loads(args['predictions_path'].read_text())[0]['mot_frame']==1
    s=i.infer_split(**args)
    assert s['videos_resumed']==2 and len(calls)==1
    # Invalidate only B by replacing it (A should be reused).
    b.path.write_bytes(b'b-modified')
    cv.captures[str(b.path)]=Capture(frames(2))
    s=i.infer_split(**args)
    assert s['videos_resumed']==1 and len(calls)==2
    # B now has an unreadable video; save an error while preserving A.
    b.path.write_bytes(b'b-new')
    cv.captures[str(b.path)]=Capture([],opened=False)
    with pytest.raises(RuntimeError,match='incomplete'):
        i.infer_split(**args)
    stats=list(csv.DictReader(args['status_path'].open()))
    assert [x['status'] for x in stats]==['ok','error','unavailable']
    assert json.loads(args['summary_path'].read_text())['videos_failed']==1


def test_unknown_download_error_is_not_skipped(tmp_path,monkeypatch):
    t=task('A',frames=2,path=tmp_path/'A.mp4')
    t=i.Task(t.split,t.site,t.video_stem,t.path,'error',t.gt_nb_frames,t.gt_width,t.gt_height)
    t.path.write_bytes(b'video')
    monkeypatch.setattr(i,'_merge_parquets',lambda *args: None)
    monkeypatch.setattr(i,'_arrow',lambda: (None,None))
    args=dict(tasks=[t],settings=i.Settings('botsort.yaml',.1,.7,640,'0'),
              model_path=tmp_path/'m.pt',cache_dir=tmp_path/'cache',
              predictions_path=tmp_path/'p.parquet',status_path=tmp_path/'s.csv',
              summary_path=tmp_path/'summary.json',backend_factory=lambda _:None,
              cv2_module=CV2({}),ultralytics_version='test')
    args['model_path'].write_bytes(b'model')
    with pytest.raises(RuntimeError,match='incomplete'):
        i.infer_split(**args)
    assert json.loads(args['summary_path'].read_text())['videos_failed']==1


def test_zero_detection_video_is_successful_with_zero_predictions():
    class EmptyModel:
        predictor = None
        def track(self, source, **kwargs):
            return [pred(Boxes([]))]
    t=task('empty',frames=3)
    cv=CV2({str(t.path):Capture(frames(3))})
    rows, stats=i.infer_video(
        t,EmptyModel(),i.Settings('botsort.yaml',.05,.7,640,'0'),
        capture_factory=cv.VideoCapture,cv2_module=cv,
    )
    assert rows == []
    assert stats['frames_decoded']==3
    assert stats['predictions_written']==0
    assert stats['unique_track_ids']==0
