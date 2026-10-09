from pathlib import Path
import yaml


def test_stage_commands_and_params():
    root=Path(__file__).resolve().parents[1]
    dvc=yaml.safe_load((root/'dvc.yaml').read_text())['stages']
    for stage in ('evaluate_tracking_metrics','evaluate_fish_counts'):
        cfg=dvc[stage]['do']
        assert dvc[stage]['foreach']==['val','test']
        assert '${item}_predictions.parquet' in cfg['cmd']
        assert '${item}_inference_status.csv' in cfg['cmd']
        assert not any('/mot_gt/' in out for out in cfg.get('outs',[]))
    params=yaml.safe_load((root/'params.yaml').read_text())
    assert params['tracking_eval']['metric_annotation_scope']=='observed'
    assert params['count_eval']['tracking_thresh']==10
