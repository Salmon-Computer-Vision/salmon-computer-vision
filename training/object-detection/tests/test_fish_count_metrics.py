import csv
import json
import math

import pytest

from object_detection.tracking_eval.count_metrics import (
    CountSettings, count_track_events, aggregate_counts, aggregate_site_direction, evaluate_counts, load_class_names,
)
from object_detection.tracking_eval.eval_common import write_csv


def row(frame, x, *, tid=1, cls=0, conf=.9, w=10, h=6, y=4, rot=0):
    return dict(frame_idx=frame, track_id=tid, class_id=cls, confidence=conf,
                x_px=x, y_px=y, width_px=w, height_px=h, rotation_deg=rot)


def test_right_and_left_deployment_semantics():
    rows = [row(0, 5), row(1, 65), row(0, 70, tid=2), row(1, 5, tid=2)]
    events = count_track_events(rows, frame_width=100, frame_height=50,
                                settings=CountSettings(), ground_truth=False)
    assert {(e['track_id'],e['direction']) for e in events} == {(1, 'r'), (2, 'l')}


def test_no_crossing_no_count():
    e = count_track_events([row(0, 5), row(2, 15)], frame_width=100, frame_height=50,
        settings=CountSettings(), ground_truth=False)
    assert e == []


def test_boundary_equality_matches_deployment():
    # Exact midpoint at the first observation does not count either direction.
    assert count_track_events([row(0,45), row(1,60)], frame_width=100, frame_height=50,
        settings=CountSettings(), ground_truth=False) == []
    assert count_track_events([row(0,1), row(1,45)], frame_width=100, frame_height=50,
        settings=CountSettings(), ground_truth=False)[0]['direction'] == 'r'


def test_all_votes_and_confidence_votes():
    rows = [row(0, 5, cls=0, conf=.1), row(1,35,cls=1,conf=.9), row(2,70,cls=0,conf=.1)]
    a = count_track_events(rows, frame_width=100, frame_height=50,
        settings=CountSettings(vote_method='all'),ground_truth=False)
    b = count_track_events(rows, frame_width=100, frame_height=50,
        settings=CountSettings(vote_method='confidence'),ground_truth=False)
    assert a[0]['class_id'] == 0
    assert b[0]['class_id'] == 1


def test_ignore_thin_voting_only():
    rows = [row(0,5,cls=3,w=3,h=9),row(1,70,cls=2,w=10,h=4)]
    e = count_track_events(rows,frame_width=100,frame_height=50,
        settings=CountSettings(vote_method='ignore_thin'),ground_truth=False)
    assert e[0]['class_id'] == 2


def test_roi_filters_trajectory_not_votes():
    rows = [row(0,5,y=35),row(1,60,y=5),row(2,70,y=5)]
    e = count_track_events(rows,frame_width=100,frame_height=50,
        settings=CountSettings(drop_bounding_boxes=True,bound_line_ratio=.5),ground_truth=False)
    assert e == []  # only eligible points are right of the line


def test_roi_restricts_and_keeps_eligible_centers():
    rows = [row(0,65,y=40),row(1,10,y=6),row(2,70,y=6)]
    e = count_track_events(rows,frame_width=100,frame_height=50,
        settings=CountSettings(drop_bounding_boxes=True,bound_line_ratio=.5),ground_truth=False)
    assert len(e) == 1 and e[0]['direction'] == 'r'


def test_gap_threshold_segments_track():
    rows = [row(0,5), row(1,70), row(20,5), row(21,70)]
    e = count_track_events(rows,frame_width=100,frame_height=50,
        settings=CountSettings(tracking_thresh=10),ground_truth=False)
    assert len(e) == 2
    assert [ev['segment'] for ev in e] == [0,1]


def test_gt_rotation_uses_rotated_box_center():
    # Top-left anchor at x=50, rotated positive 90 degrees; its center moves left.
    rows = [row(0,5,rot=0,w=20,h=10), row(1,90,rot=90,w=20,h=10)]
    ev = count_track_events(rows,frame_width=100,frame_height=80,
        settings=CountSettings(),ground_truth=True)
    assert ev and ev[0]['direction']=='r'


def test_zero_gt_null_nmae(tmp_path, monkeypatch):
    from object_detection.tracking_eval import eval_common
    import object_detection.tracking_eval.count_metrics as mod
    seq = [dict(split='val',video_stem='empty',site='river',nb_frames=2,n_gt_rows=0,
                n_tracks=0,rotated_rows=0,status='no_tracks',width=100,height=50,fps=10)]
    status = [dict(split='val',video_stem='empty',status='ok',eligible_for_evaluation=True,
                   frames_decoded=2,predictions_written=0)]
    write_csv(tmp_path/'seq.csv',seq,list(seq[0]))
    write_csv(tmp_path/'status.csv',status,list(status[0]))
    write_csv(tmp_path/'gt.csv',[],['split','video_stem','frame_idx','mot_frame','track_id','class_id',
                                     'x_px','y_px','width_px','height_px','rotation_deg'])
    (tmp_path/'data.yaml').write_text('names: [Sockeye, Coho]\n')
    write_csv(tmp_path/'coverage.csv',[dict(video_stem='empty',fully_annotated=True)],['video_stem','fully_annotated'])
    monkeypatch.setattr(eval_common,'iter_parquet_predictions',lambda _:iter([]))
    result=evaluate_counts(gt_csv=tmp_path/'gt.csv',sequence_csv=tmp_path/'seq.csv',
        inference_status_csv=tmp_path/'status.csv',predictions_parquet=tmp_path/'noparquet',
        data_yaml=tmp_path/'data.yaml',split='val',settings=CountSettings(),
        scope='verified',coverage_csv=tmp_path/'coverage.csv',summary_json=tmp_path/'summary.json',
        per_group_csv=tmp_path/'group.csv',per_video_csv=tmp_path/'video.csv',
        per_site_csv=tmp_path/'site.csv',
        events_csv=tmp_path/'events.csv',coverage_csv_out=tmp_path/'coverage-out.csv')
    assert result['nMAE_class_direction'] is None
    assert result['gt_events'] == result['pred_events'] == 0
    assert len(list(csv.DictReader((tmp_path/'video.csv').open()))) == 1


def test_class_name_mapping(tmp_path):
    p=tmp_path/'d.yaml'
    p.write_text('names:\n  0: Sockeye\n  4: Chum\n')
    assert load_class_names(p)=={0:'Sockeye',4:'Chum'}


def test_signed_bias_and_per_group_sum():
    selection={'a':{'site':'river'},'b':{'site':'river'}}
    events=[dict(video_stem='a',source='gt',class_id=0,direction='r'),
            dict(video_stem='a',source='pred',class_id=1,direction='r'),
            dict(video_stem='b',source='pred',class_id=0,direction='l')]
    detail,video=aggregate_counts(events,selection,{0:'Sockeye',1:'Coho'},'val')
    assert sum(x['absolute_error'] for x in detail)==3
    assert len(video)==2
    assert video[0]['absolute_error']==0 # equal totals, but wrong class
    assert video[1]['absolute_error']==1


def test_vote_no_eligible_class():
    assert count_track_events([row(0,5,w=2,h=10),row(1,70,w=2,h=10)],
        frame_width=100,frame_height=50,settings=CountSettings(vote_method='ignore_thin'),
        ground_truth=False)==[]


def test_invalid_config_and_duplicate_frames():
    with pytest.raises(ValueError):
        CountSettings(vote_method='oops').validate()
    with pytest.raises(ValueError,match='Duplicate'):
        count_track_events([row(0,5),row(0,70)],frame_width=100,frame_height=50,
                           settings=CountSettings(),ground_truth=False)


def test_site_species_direction_aggregate_denominator():
    selected={'a':{'site':'river'},'b':{'site':'river'}}
    detail=[dict(site='river',class_id=0,class_name='Sockeye',direction='r',
                 gt_count=2,pred_count=1,absolute_error=1)]
    rows=aggregate_site_direction(detail,selected,'test')
    assert len(rows)==1
    assert rows[0]['num_videos']==2
    assert rows[0]['MAE_per_video']==.5
    assert rows[0]['nMAE']==.5
