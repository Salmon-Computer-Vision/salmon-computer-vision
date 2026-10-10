"""Unit/integration tests for site annotation statistics DVC plots."""
import csv
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aggregate_site_class_stats.py"
spec = importlib.util.spec_from_file_location("aggregate_site_class_stats", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_rows(path: Path, site: str, kind: str, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "frame":
        fields = ["site", "class_id", "class_name", "frame_count", "frame_pct_within_class", "frame_pct_within_site"]
    else:
        fields = ["site", "class_id", "class_name", "box_count", "box_pct_within_class", "box_pct_within_site"]
    with path.open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for cls, name, count in rows:
            writer.writerow({'site':site, 'class_id':cls, 'class_name':name, fields[3]:count,
                             fields[4]:100.0 if count else 0,fields[5]:100.0 if count else 0})


def setup(tmp_path):
    sites=['stephenssmolt','koeye']
    cfg=tmp_path/'params.yaml'
    cfg.write_text(yaml.safe_dump({'data':{'sites':sites}}))
    src=tmp_path/'sites'
    for kind in ('frame','box'):
        filename=mod.KIND_SPECS[kind][0]
        write_rows(src/'stephenssmolt'/'yolo_annos_stats'/filename, 'stephenssmolt',kind,[(0,'Sockeye',2 if kind=='frame' else 10),(1,'Coho',4)])
        write_rows(src/'koeye'/'yolo_annos_stats'/filename, 'koeye',kind,[(0,'Sockeye',6 if kind=='frame' else 30),(1,'Coho',0)])
    return cfg,src


def rows_by_key(path):
    with path.open(newline='',encoding='utf8') as f:
        return {(r['site'],int(r['class_id'])):r for r in csv.DictReader(f)}


def test_cross_site_share_not_per_site_hardcoded_100(tmp_path):
    cfg,src=setup(tmp_path)
    out=tmp_path/'out'
    mod.main(['--params-yaml',str(cfg),'--sites-root',str(src),'--out-dir',str(out)])
    frame=rows_by_key(out/'site_class_frame_counts.csv')
    assert len(frame)==4
    assert int(frame['stephenssmolt',0]['frame_count'])==2
    assert float(frame['stephenssmolt',0]['frame_pct_within_class'])==25
    assert float(frame['koeye',0]['frame_pct_within_class'])==75
    assert float(frame['stephenssmolt',1]['frame_pct_within_class'])==100
    assert float(frame['koeye',1]['frame_pct_within_class'])==0
    assert float(frame['stephenssmolt',0]['frame_pct_within_site'])==pytest.approx(33.333333,abs=.00001)
    assert float(frame['koeye',0]['frame_pct_within_site'])==100
    box=rows_by_key(out/'site_class_box_counts.csv')
    assert int(box['stephenssmolt',0]['box_count'])==10
    assert int(box['koeye',0]['box_count'])==30
    assert float(box['stephenssmolt',0]['box_pct_within_class'])==25
    assert float(box['koeye',0]['box_pct_within_class'])==75


def test_missing_site_fails_instead_of_silent_omission(tmp_path):
    cfg,src=setup(tmp_path)
    (src/'koeye'/'yolo_annos_stats'/'site_class_frame_counts.csv').unlink()
    with pytest.raises(FileNotFoundError,match='build_model_input@koeye'):
        mod.main(['--params-yaml',str(cfg),'--sites-root',str(src),'--out-dir',str(tmp_path/'out')])


def test_wrong_site_row_fails(tmp_path):
    cfg,src=setup(tmp_path)
    path=src/'stephenssmolt'/'yolo_annos_stats'/'site_class_frame_counts.csv'
    write_rows(path,'oops','frame',[(0,'Sockeye',2)])
    with pytest.raises(ValueError,match='does not match'):
        mod.aggregate_kind(src,mod.read_site_names(cfg),tmp_path/'out','frame')


def test_class_mapping_mismatch_fails(tmp_path):
    cfg,src=setup(tmp_path)
    path=src/'koeye'/'yolo_annos_stats'/'site_class_frame_counts.csv'
    write_rows(path,'koeye','frame',[(0,'Coho',5)])
    with pytest.raises(ValueError,match='maps to both'):
        mod.aggregate_kind(src,mod.read_site_names(cfg),tmp_path/'out','frame')


def test_negative_count_and_duplicate_site_fails(tmp_path):
    cfg,src=setup(tmp_path)
    path=src/'koeye'/'yolo_annos_stats'/'site_class_frame_counts.csv'
    write_rows(path,'koeye','frame',[(0,'Sockeye',-2)])
    with pytest.raises(ValueError,match='negative'):
        mod.aggregate_kind(src,mod.read_site_names(cfg),tmp_path/'out','frame')
    cfg.write_text(yaml.safe_dump({'data':{'sites':['koeye','koeye']}}))
    with pytest.raises(ValueError,match='duplicates'):
        mod.read_site_names(cfg)


def test_dvc_stage_named_plots_and_templates():
    dvc=yaml.safe_load((ROOT/'dvc.yaml').read_text())
    assert 'plot_site_class_stats' not in dvc['stages']
    stage=dvc['stages']['aggregate_site_class_stats']
    assert stage['deps'] == [
        'scripts/aggregate_site_class_stats.py',
        'data/02_interim/annotation_stats_by_site',
    ]
    assert 'data.sites' in stage['params']
    assert '--sites-root data/02_interim/annotation_stats_by_site' in stage['cmd']
    collector = dvc['stages']['collect_site_class_stats']
    assert collector['foreach'] == '${data.sites}'
    assert len(collector['do']['deps']) == 2
    assert len(collector['do']['outs']) == 1
    assert '${item}' in collector['do']['cmd']
    # No named site appears as an aggregate dependency.
    assert all('stephenssmolt' not in dep and 'koeye' not in dep for dep in stage['deps'])
    assert len(stage['outs'])==2
    names=[next(iter(item)) for item in dvc['plots'] if isinstance(item,dict)]
    assert len(set(names))==len(names)
    for plot_name in ['annotation_frame_counts','annotation_box_counts','annotation_frame_share','annotation_box_share']:
        assert plot_name in names
        plot=next(item[plot_name] for item in dvc['plots'] if isinstance(item,dict) and plot_name in item)
        for source in plot['y']:
            assert source in stage['outs']
        template=ROOT/plot['template']
        obj=json.loads(template.read_text())
        assert obj['data']['values']=='<DVC_METRIC_DATA>'
        assert '<DVC_METRIC_Y>' in json.dumps(obj)


def test_dynamic_site_selection_end_to_end(tmp_path):
    # Emulate the foreach collector commands and the normal aggregation CLI.
    # The site set can change without modifying dvc.yaml or the aggregator.
    dvc = yaml.safe_load((ROOT / 'dvc.yaml').read_text())
    collector = dvc['stages']['collect_site_class_stats']['do']
    params, original = setup(tmp_path)
    workroot = tmp_path / 'data' / '02_interim'
    source = workroot / 'sites'
    source.parent.mkdir(parents=True, exist_ok=True)
    # Relocate test CSVs to the relative paths declared by the DVC stage.
    import shutil
    shutil.copytree(original, source)

    def collect(site: str) -> None:
        cmd = collector['cmd'].replace('${item}', site)
        subprocess.run(cmd, shell=True, cwd=tmp_path, check=True)

    for site in ['stephenssmolt', 'koeye']:
        collect(site)
    out = tmp_path / 'out'
    stats_root = workroot / 'annotation_stats_by_site'
    mod.main(['--params-yaml', str(params), '--sites-root', str(stats_root), '--out-dir', str(out)])
    assert len(rows_by_key(out / 'site_class_frame_counts.csv')) == 4

    # Add a third arbitrary site and change params: no hard-coded YAML deps needed.
    for kind in ('frame', 'box'):
        name = mod.KIND_SPECS[kind][0]
        write_rows(source / 'new_site' / 'yolo_annos_stats' / name,
                   'new_site', kind, [(0, 'Sockeye', 8), (1, 'Coho', 2)])
    collect('new_site')
    params.write_text(yaml.safe_dump({'data': {'sites': ['koeye', 'new_site']}}))
    mod.main(['--params-yaml', str(params), '--sites-root', str(stats_root), '--out-dir', str(out)])
    rows = rows_by_key(out / 'site_class_frame_counts.csv')
    assert {site for site, _ in rows} == {'koeye', 'new_site'}
    assert int(rows['new_site', 0]['frame_count']) == 8
    assert float(rows['koeye', 0]['frame_pct_within_class']) == pytest.approx(100 * 6 / 14)
    assert float(rows['new_site', 0]['frame_pct_within_class']) == pytest.approx(100 * 8 / 14)

    # Removing a site doesn't accidentally retain it in the aggregate.
    params.write_text(yaml.safe_dump({'data': {'sites': ['new_site']}}))
    mod.main(['--params-yaml', str(params), '--sites-root', str(stats_root), '--out-dir', str(out)])
    assert {site for site, _ in rows_by_key(out / 'site_class_frame_counts.csv')} == {'new_site'}
