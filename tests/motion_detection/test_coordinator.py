from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
import pytest
from pysalmcount.motion_detect_stream import MotionEventCoordinator as Coordinator, TickAction as Action

@pytest.fixture
def coord(tmp_path, clock):
    return Coordinator(['top', 'bottom'], max_clip_seconds=10, post_roll_seconds=5,
        composite_out_dir=tmp_path, composite_save_prefix='device', composite_fps=10,
        composite_timeout_seconds=20)

@pytest.mark.parametrize('names', [[], ['a'], ['a', 'a']])
def test_invalid_camera_list(names):
    with pytest.raises(ValueError):
        Coordinator(names)

def test_idle_and_unknown_camera(coord):
    assert coord.tick('top', False) is Action.CONTINUE
    assert not coord.take_trigger('unknown')
    with pytest.raises(ValueError, match='Unknown'):
        coord.enter_event('unknown')
    with pytest.raises(RuntimeError, match='idle'):
        coord.get_current_clip_info()

def test_fanout_and_shared_identity(coord):
    first = coord.enter_event('top')
    assert not coord.take_trigger('top')
    assert coord.take_trigger('bottom')
    assert not coord.take_trigger('bottom')
    assert coord.enter_event('bottom') == first
    assert first.part_number == 1
    assert first.originator == 'top'
    assert first.event_start_ts.utcoffset().total_seconds() == 0

def test_simultaneous_enter_mints_only_one_event(coord):
    barrier = threading.Barrier(2)
    def join(name):
        barrier.wait(timeout=5)
        return coord.enter_event(name)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(join, ['top', 'bottom']))
    assert results[0] == results[1]
    assert not coord.take_trigger('top')
    assert not coord.take_trigger('bottom')

def test_motion_on_either_camera_extends_event(coord, clock):
    coord.enter_event('top'); coord.enter_event('bottom')
    clock.now += 4
    assert coord.tick('bottom', True) is Action.CONTINUE
    clock.now += 4
    assert coord.tick('top', False) is Action.CONTINUE
    clock.now += 1
    assert coord.tick('top', False) is Action.FINALIZE
    assert coord.tick('bottom', False) is Action.FINALIZE

def test_rollover_broadcasts_once_without_changing_event(coord, clock):
    original = coord.enter_event('top'); coord.enter_event('bottom')
    clock.now += 10
    assert coord.tick('top', True) is Action.ROLLOVER
    assert coord.tick('bottom', True) is Action.ROLLOVER
    assert coord.tick('bottom', True) is Action.CONTINUE
    current = coord.get_current_clip_info()
    assert current.part_number == 2
    assert current.event_id == original.event_id
    assert current.event_start_ts == original.event_start_ts

def test_finalize_wins_over_rollover_and_prevents_rejoin(coord, clock):
    original = coord.enter_event('top'); coord.enter_event('bottom')
    clock.now += 10
    assert coord.tick('top', False) is Action.FINALIZE
    coord.leave_event('top')
    assert coord.enter_event('top') is None
    assert coord.consume_finalize_if_pending('bottom')
    assert not coord.consume_finalize_if_pending('bottom')
    coord.leave_event('bottom'); coord.leave_event('bottom')
    assert not coord.is_event_active()
    assert not coord.take_trigger('bottom')
    assert coord.enter_event('top').event_id != original.event_id

def test_finalize_cancels_unconsumed_rollover(coord, clock):
    coord.enter_event('top'); coord.enter_event('bottom')
    clock.now += 10
    assert coord.tick('top', True) is Action.ROLLOVER
    clock.now += 5
    assert coord.tick('top', False) is Action.FINALIZE
    assert coord.tick('bottom', False) is Action.FINALIZE

def test_completion_barrier_order_dedup_and_after_leave(coord):
    info = coord.enter_event('top'); coord.leave_event('top')
    assert coord.report_part_finished('bottom', info, {'path': 'bottom.mp4'}) is None
    assert coord.report_part_finished('bottom', info, {'path': 'bottom.mp4'}) is None
    job = coord.report_part_finished('top', info, {'path': 'top.mp4'})
    assert [s.cam_name for s in job.sources] == ['top', 'bottom']
    assert [s.path for s in job.sources] == [Path('top.mp4'), Path('bottom.mp4')]
    assert job.event_id == info.event_id
    assert coord.report_part_finished('top', info, {'path': 'late.mp4'}) is None
    assert coord.reap_stale_parts(force=True) == []

@pytest.mark.parametrize('force', [False, True])
def test_partial_timeout_missing_camera_and_late_result(coord, clock, force):
    info = coord.enter_event('top')
    coord.report_part_finished('top', info, {'path': 'top.mp4'})
    clock.now += 19.9
    assert coord.reap_stale_parts() == []
    if not force:
        clock.now += .1
    jobs = coord.reap_stale_parts(force=force)
    assert len(jobs) == 1
    assert jobs[0].sources[1].path is None
    assert coord.report_part_finished('bottom', info, {'path': 'late.mp4'}) is None
    assert coord.reap_stale_parts(force=True) == []
