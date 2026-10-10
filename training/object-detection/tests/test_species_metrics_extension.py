from __future__ import annotations
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from object_detection.tracking_eval.eval_common import write_csv
from object_detection.tracking_eval.species_metrics import (
    partition_gt_by_species, species_sequence_info, evaluate_species_tracking,
    SPECIES_COLUMNS,
)
from object_detection.tracking_eval.count_metrics import aggregate_species_directional
from object_detection.tracking_eval.tracking_metrics import evaluate_tracking


def _seq(stem, n_gt, status="ok", site="river"):
    return dict(split="val", video_stem=stem, site=site, status=status,
                width=100, height=60, fps=10, nb_frames=3,
                n_gt_rows=n_gt, n_tracks=(1 if n_gt else 0), rotated_rows=0)


def _gt(stem="a", cls=0, idx=0, tid=1):
    return dict(split="val", video_stem=stem, frame_idx=idx, mot_frame=idx+1,
                track_id=tid, class_id=cls, x_px=5 + 25*idx, y_px=5,
                width_px=15, height_px=10, rotation_deg=0)


def _pred(stem="a", cls=0, idx=0, tid=1):
    return dict(split="val", video_stem=stem, frame_idx=idx, mot_frame=idx+1,
                track_id=tid, class_id=cls, confidence=.8, x_px=5+25*idx,
                y_px=5, width_px=15, height_px=10)


class FakeDataset:
    def __init__(self, config):
        self.config = config
    def get_name(self): return "MotChallenge2DBox"


class FakeEvaluator:
    def __init__(self, config): self.config = config
    def evaluate(self, datasets, metrics):
        ds = datasets[0]
        assert ds.config["DO_PREPROC"] is False
        names = Path(ds.config["SEQMAP_FILE"]).read_text().splitlines()[1:]
        assert names
        tracker = ds.config["TRACKERS_TO_EVAL"][0]
        def report():
            return {"HOTA": {"HOTA": [.7, .5], "DetA": [.6, .4], "AssA": [.8, .6]},
                    "CLEAR": {"MOTA": .3, "MOTP": .9, "CLR_FP": 2, "CLR_FN": 1,
                              "CLR_TP": 3, "IDSW": 1},
                    "Identity": {"IDF1": .55, "IDP": .6, "IDR": .5}}
        vals = {stem: {"pedestrian": report()} for stem in names}
        vals["COMBINED_SEQ"] = {"pedestrian": report()}
        return {ds.get_name(): {tracker: vals}}, {ds.get_name(): {tracker: "Success"}}


def _backend():
    return SimpleNamespace(datasets=SimpleNamespace(MotChallenge2DBox=FakeDataset),
                           Evaluator=FakeEvaluator,
                           metrics=SimpleNamespace(HOTA=lambda: 0, CLEAR=lambda: 0, Identity=lambda: 0))


def test_species_partition_and_prediction_only_negative(tmp_path, monkeypatch):
    import object_detection.tracking_eval.species_metrics as species
    seqs = {"a": _seq("a", 2), "b": _seq("b", 0, "no_tracks")}
    path = tmp_path / "gt.csv"
    write_csv(path, [_gt(idx=0), _gt(idx=1)], list(_gt()))
    pred = {"a": [_pred(cls=0), _pred(cls=1, idx=1)], "b": [_pred(stem="b", cls=1)]}
    # Coho has no GT but has predictions => FP diagnostic, NOT a HOTA score.
    report = evaluate_species_tracking(gt_csv=path, selected=seqs,
        predictions=pred, names={0:"Sockeye", 1:"Coho", 2:"Chum"},
        split="val", benchmark="SalmonVision", tracker="botsort",
        temp_path=tmp_path/"temp", backend=_backend())
    assert len(report) == 3
    assert report[0]["status"] == "scored"
    assert report[0]["HOTA"] == pytest.approx(.6)
    assert report[0]["gt_detections"] == 2
    assert report[0]["pred_detections"] == 1
    assert report[0]["evaluated_sequences"] == 1
    assert report[1]["status"] == "no_gt"
    assert report[1]["FP"] == 2 and report[1]["HOTA"] is None
    assert report[1]["evaluated_sequences"] == 2
    assert report[2]["status"] == "no_gt" and report[2]["FP"] == 0
    assert list((tmp_path/"temp"/"partition").glob("species_*.csv"))


def test_species_with_gt_and_false_positives_in_negative(tmp_path):
    seqs = {"a": _seq("a", 1), "b": _seq("b", 0, "no_tracks")}
    path = tmp_path / "gt.csv"
    write_csv(path, [_gt()], list(_gt()))
    pred = {"a": [_pred()], "b": [_pred(stem="b")]}
    result = evaluate_species_tracking(gt_csv=path, selected=seqs, predictions=pred,
        names={0:"Sockeye"}, split="val",benchmark="SalmonVision",tracker="bt",
        temp_path=tmp_path/"temp",backend=_backend())
    assert result[0]["evaluated_sequences"] == 2
    assert result[0]["pred_sequences"] == 2


def test_class_switches_frame_filtered(tmp_path, monkeypatch):
    import object_detection.tracking_eval.species_metrics as sp
    original = sp.make_mot_workspace
    observed = {}
    def wrap(**kwargs):
        observed['class0'] = kwargs['predictions']
        return original(**kwargs)
    monkeypatch.setattr(sp,'make_mot_workspace',wrap)
    seqs={"a":_seq("a", 2)}
    path=tmp_path/'gt.csv'
    write_csv(path,[_gt(idx=0),_gt(idx=1)],list(_gt()))
    evaluate_species_tracking(gt_csv=path,selected=seqs,
        predictions={'a':[_pred(idx=0),_pred(cls=1,idx=1)]},names={0:'Sockeye',1:'Coho'},
        split='val',benchmark='SalmonVision',tracker='bt',temp_path=tmp_path/'temp',backend=_backend())
    assert len(observed['class0']['a']) == 1
    assert observed['class0']['a'][0]['mot_frame'] == 1


def test_unknown_species_fails_loudly(tmp_path):
    seqs={'a':_seq('a',1)}
    path=tmp_path/'gt.csv'
    write_csv(path,[_gt(cls=19)],list(_gt()))
    with pytest.raises(ValueError,match='Unknown GT class'):
        evaluate_species_tracking(gt_csv=path,selected=seqs,predictions={},
            names={0:'Sockeye'},split='val',benchmark='SV',tracker='bt',
            temp_path=tmp_path/'temp',backend=_backend())


def test_count_species_sum_absolute_before_aggregating():
    rows=[dict(class_id=0,gt_count=1,pred_count=0,absolute_error=1),
          dict(class_id=0,gt_count=0,pred_count=1,absolute_error=1)]
    report=aggregate_species_directional(rows,{'a':{},'b':{}},{0:'Sockeye',1:'Coho'},'test')
    sock, coho = report
    assert sock['gt_count'] == sock['pred_count'] == 1
    assert sock['signed_error']==0
    assert sock['absolute_error_sum']==2
    assert sock['MAE_per_video']==1 and sock['nMAE']==2
    assert coho['nMAE'] is None and coho['MAE_per_video']==0


def test_species_gt_for_both_classes(tmp_path):
    seqs={'a':_seq('a',2),'b':_seq('b',1)}
    path=tmp_path/'gt.csv'
    write_csv(path,[_gt(idx=0),_gt(idx=1),_gt(stem='b',cls=1)],list(_gt()))
    res=evaluate_species_tracking(gt_csv=path,selected=seqs,predictions={'a':[],'b':[]},
        names={0:'Sockeye',1:'Coho'},split='val',benchmark='SV',tracker='bt',
        temp_path=tmp_path/'temp',backend=_backend())
    assert all(x['status']=='scored' for x in res)
    assert res[0]['gt_detections']==2
    assert res[1]['gt_detections']==1


def test_cli_passes_species_args(monkeypatch,tmp_path):
    import object_detection.tracking_eval.count_metrics as count
    import object_detection.tracking_eval.tracking_metrics as tracking
    got={}
    def fake_count(**kw): got['count']=kw; return {'ok':True}
    def fake_track(**kw): got['track']=kw; return {'ok':True}
    monkeypatch.setattr(count,'evaluate_counts',fake_count)
    monkeypatch.setattr(tracking,'evaluate_tracking',fake_track)
    count.main(['--gt-csv','a','--sequences-csv','b','--inference-status-csv','c',
          '--predictions-parquet','d','--data-yaml','e','--split','val','--summary-json','f',
          '--per-group-csv','g','--per-video-csv','h','--per-site-csv','i',
          '--per-species-csv','species.csv','--events-csv','j','--coverage-output-csv','k'])
    tracking.main(['--gt-csv','a','--sequences-csv','b','--inference-status-csv','c',
          '--predictions-parquet','d','--split','val','--benchmark','SV','--tracker','bt',
          '--workdir-root','w','--summary-json','f','--per-sequence-csv','g',
          '--coverage-output-csv','k','--data-yaml','e','--per-species-csv','species.csv'])
    assert got['count']['per_species_csv']==Path('species.csv')
    assert got['track']['per_species_csv']==Path('species.csv')


def test_dvc_plots_exist_and_fields():
    import yaml
    p=Path(__file__).resolve().parents[1]
    dvc=yaml.safe_load((p/'dvc.yaml').read_text())
    for stage,filename in [('evaluate_tracking_metrics','tracking_per_species.csv'),
                            ('evaluate_fish_counts','count_per_species.csv')]:
        cfg=dvc['stages'][stage]['do']
        assert '--per-species-csv' in cfg['cmd']
        assert any(filename in str(k) for item in cfg['plots'] for k in item)
    for template in (p/'config/plots').glob('*.json'):
        spec=json.loads(template.read_text())
        assert spec['data']['values']=='<DVC_METRIC_DATA>'
        assert 'facet' in spec
