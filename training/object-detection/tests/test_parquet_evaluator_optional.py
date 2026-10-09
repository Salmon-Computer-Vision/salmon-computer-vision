"""Optional end-to-end Parquet smoke test (run after uv add pyarrow)."""
import pytest

pa = pytest.importorskip('pyarrow')
pq = pytest.importorskip('pyarrow.parquet')

from object_detection.tracking_eval.eval_common import predictions_by_video, write_csv


def test_real_parquet_empty_and_sorted(tmp_path):
    records = [dict(split='val', video_stem='fish', frame_idx=i, mot_frame=i+1,
        track_id=1, class_id=0, confidence=.8, x_px=float(i), y_px=1.0,
        width_px=10.0, height_px=5.0) for i in (1,0)]
    p=tmp_path/'real.parquet'
    pq.write_table(pa.Table.from_pylist(records),p)
    s=tmp_path/'inference.csv'
    statuses=[dict(split='val',video_stem='fish',predictions_written=2)]
    write_csv(s,statuses,list(statuses[0]))
    selected={'fish':{'nb_frames':3}}
    rows=predictions_by_video(p,split='val',selected=selected,inference_status_csv=s)
    assert [r['frame_idx'] for r in rows['fish']] == [0,1]
