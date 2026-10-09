"""Check stage integration against the current drop-in YAML."""
from pathlib import Path

import yaml


def test_tracking_inference_dvc_stage_contract():
    root = Path(__file__).resolve().parents[1]
    stage = yaml.safe_load((root/'dvc.yaml').read_text())['stages']['run_tracking_inference']
    assert stage['foreach'] == ['val','test']
    item = stage['do']
    cmd = item['cmd']
    assert 'scripts/run_tracking_inference.py' in cmd
    assert '--predictions-parquet data/03_processed/tracking_eval/${item}_predictions.parquet' in cmd
    assert '--download-status-csv data/03_processed/tracking_eval/${item}_video_download_status.csv' in cmd
    assert '--sequences-csv data/03_processed/tracking_eval/${item}_sequences.csv' in cmd
    assert '--model ${config.dataset}/salmon_dataset/training/yolov8n_full/${train.run_name}/weights/best.pt' in cmd
    assert '--cache-dir ' in cmd
    assert 'always_changed' not in item
    assert not any('workdir' in str(o) or 'mot_gt/' in str(o) for o in item['outs'])
    assert len(item['outs']) == 3
    assert '${runtime.cuda}' in cmd
    assert set(item['outs']) == {
        'data/03_processed/tracking_eval/${item}_predictions.parquet',
        'data/03_processed/tracking_eval/${item}_inference_status.csv',
        'data/03_processed/tracking_eval/${item}_inference_summary.json',
    }


def test_inference_stage_does_not_replace_model_or_params():
    root=Path(__file__).resolve().parents[1]
    stages=yaml.safe_load((root/'dvc.yaml').read_text())['stages']
    expected_model='${config.dataset}/salmon_dataset/training/yolov8n_full/${train.run_name}/weights/best.pt'
    assert expected_model in stages['run_tracking_inference']['do']['deps']
    assert expected_model in stages['evaluate']['deps']
    assert stages['run_tracking_inference']['do']['params']
