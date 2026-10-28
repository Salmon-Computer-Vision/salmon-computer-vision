#!/usr/bin/env python3
"""Sequential, resumable motion extraction from YYYYMMDD/HHMM/*.h264.

Requires the previously updated pysalmcount (including rotate_90). Source files
are never modified. Each source is independently processed at its original FPS.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

LOG = logging.getLogger('batch_motion')
SCHEMA = 1
SCRIPT = Path(__file__).resolve()
PACKAGE = SCRIPT.parents[1] / 'pysalmcount' / 'pysalmcount'


def folder_timestamp(path):
    day, minute = path.parent.parent.name, path.parent.name
    if not re.fullmatch(r'\d{8}', day) or not re.fullmatch(r'\d{4}', minute):
        raise ValueError(f'Expected YYYYMMDD/HHMM/file.h264: {path}')
    return datetime.strptime(day + minute, '%Y%m%d%H%M')


def discover(root):
    """Scan numeric date/time directories, including nested dates; skip OS trees."""
    found = []
    for folder, directories, filenames in os.walk(root, followlinks=False):
        parent = Path(folder)
        directories[:] = sorted(name for name in directories
            if re.fullmatch(r"\d{8}|\d{4}", name)
            and not (parent / name).is_symlink())
        for name in sorted(filenames):
            source = parent / name
            if source.is_symlink() or source.suffix.lower() != '.h264':
                continue
            # Ignore unrelated files at the drive root, never scan system trees.
            if not re.fullmatch(r"\d{4}", parent.name) or not re.fullmatch(r"\d{8}", parent.parent.name):
                LOG.warning('Ignoring file outside YYYYMMDD/HHMM: %s', source)
                continue
            folder_timestamp(source)  # Reject invalid calendar/time values.
            if not re.fullmatch(r'[A-Za-z0-9_-]+', source.stem):
                raise ValueError(f'Unsupported channel filename: {source.name}')
            found.append(source)
    return sorted(found, key=lambda source: (folder_timestamp(source), source.relative_to(root).as_posix()))


def source_identity(source, root):
    stat = source.stat()
    return {'relative_path': source.relative_to(root).as_posix(),
            'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def pipeline_digest():
    digest = hashlib.sha256()
    for path in [SCRIPT] + [PACKAGE / name for name in (
        '__init__.py', 'dataloader.py', 'videoloader.py', 'motion_detect_stream.py',
        'clip_compositor.py', 'utils.py')]:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def signature(identity, settings):
    payload = {'schema': SCHEMA, 'source': identity, 'settings': settings,
               'pipeline_sha256': pipeline_digest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def remux_command(source, target, fps):
    # -r BEFORE -i assigns raw-input timing. Stream copy avoids recompression.
    return ['ffmpeg', '-hide_banner', '-nostdin', '-v', 'warning', '-xerror',
            '-fflags', '+genpts', '-r', str(fps), '-f', 'h264', '-i', str(source),
            '-map', '0:v:0', '-c:v', 'copy', '-an', '-avoid_negative_ts', 'make_zero',
            '-movflags', '+faststart', '-y', str(target)]


def run_checked(command, log, timeout):
    """Bound each job and kill its whole process group on timeout/interruption."""
    proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        code = proc.wait(timeout=timeout)
        if code:
            raise subprocess.CalledProcessError(code, command)
    except BaseException:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            if sig == signal.SIGTERM:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        proc.wait()
        raise


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,nb_frames,avg_frame_rate,duration',
        '-of', 'json', str(path)], check=True, capture_output=True, text=True, timeout=60)
    streams = json.loads(result.stdout)['streams']
    if not streams or int(streams[0].get('nb_frames', 0)) <= 0:
        raise RuntimeError(f'No valid frame count in {path}')
    return streams[0]


def write_json(path, payload):
    with path.open('w') as handle:
        json.dump(payload, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def is_complete(final, expected_signature):
    if not final.exists():
        return False
    marker = final / 'complete.json'
    try:
        manifest = json.loads(marker.read_text())
        if manifest['signature'] != expected_signature:
            raise ValueError('source, settings, or pipeline changed')
        for output in manifest['outputs']:
            rel = Path(output['path'])
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('invalid output path in manifest')
            if (final / rel).stat().st_size != output['size']:
                raise ValueError(f'output changed: {rel}')
        if manifest['schema'] != SCHEMA:
            raise ValueError('manifest schema changed')
        return True
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(f'Cannot resume {final}: {exc}. Use a new output directory '
                           'or move this result aside explicitly.') from exc


@contextmanager
def output_lock(root):
    with (root / '.batch.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'Another batch is using {root}') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def process_source(source, root, output, settings, timeout):
    identity = source_identity(source, root)
    stamp = folder_timestamp(source)
    key = source.relative_to(root).with_suffix('')
    final = output / 'results' / key
    expected_signature = signature(identity, settings)
    if is_complete(final, expected_signature):
        LOG.info('SKIP completed %s', identity['relative_path'])
        return 'skipped'
    if identity['size'] == 0:
        raise RuntimeError(f'Empty input file: {source}')
    workspace = output / '.work'
    workspace.mkdir(exist_ok=True)
    logs = output / 'logs' / key
    logs.mkdir(parents=True, exist_ok=True)
    # One source per staging directory. Only a completed result gets published.
    with tempfile.TemporaryDirectory(prefix='source-', dir=workspace) as name:
        work = Path(name)
        stage = work / 'result'
        stage.mkdir()
        media = work / f'input_{stamp:%Y%m%d_%H%M%S}.mp4'
        job = {'input': str(media), 'output': str(stage), 'settings': settings,
               'source': identity, 'folder_start': stamp.isoformat(),
               'prefix': settings['device_id'] + '_' + source.stem}
        job_path = work / 'job.json'
        write_json(job_path, job)
        log_path = logs / f'{work.name}.log'
        LOG.info('PROCESS %s (folder start %s); log=%s', source, stamp, log_path)
        with log_path.open('w') as log:
            run_checked(remux_command(source, media, settings['source_fps']), log, timeout)
            run_checked([sys.executable, str(SCRIPT), '_worker', str(job_path)], log, timeout)
        if source_identity(source, root) != identity:
            raise RuntimeError(f'Source changed during processing: {source}')
        worker_result = json.loads((stage / 'worker-result.json').read_text())
        outputs = [{'path': p.relative_to(stage).as_posix(), 'size': p.stat().st_size}
                   for p in sorted(stage.rglob('*')) if p.is_file()]
        write_json(stage / 'complete.json', {
            'schema': SCHEMA, 'signature': expected_signature, 'source': identity,
            'folder_start': stamp.isoformat(), 'settings': settings,
            'worker': worker_result, 'outputs': outputs,
            'timestamp_convention': 'folder clock plus motion-trigger frame / source FPS; no timezone conversion',
        })
        final.parent.mkdir(parents=True, exist_ok=True)
        os.rename(stage, final)
    LOG.info('DONE %s -> %s', source, final)
    return 'processed'


def worker(job_path):
    """Fresh process per source; reuse the real detector without CLI refactors."""
    import multiprocessing as mp
    sys.path.insert(0, str(PACKAGE.parent))
    from pysalmcount import motion_detect_stream as md, videoloader as vl, utils
    mp.set_start_method('spawn', force=True)
    job = json.loads(Path(job_path).read_text())
    cfg = job['settings']
    media, out = Path(job['input']), Path(job['output'])
    metadata = probe(media)
    expected_frames = int(metadata['nb_frames'])
    numerator, denominator = map(int, metadata['avg_frame_rate'].split('/'))
    if denominator == 0 or not math.isclose(numerator / denominator, cfg['source_fps'], rel_tol=.001):
        raise RuntimeError(f'Remux frame rate disagrees with source FPS: {metadata}')

    class CountingLoader(vl.VideoLoader):
        processed_frames = 0
        def items(self):
            for item in super().items():
                self.processed_frames += 1
                yield item

    # No downsampling: frame_counter / fps remains the original elapsed time.
    loader = CountingLoader([str(media)], target_fps=None, buffer_size=4)
    detector = md.MotionDetector(loader, out, save_video=True, save_cont_video=False,
                                is_video=True, save_prefix=job['prefix'])
    utils.ping_in_background = lambda url: None  # No live-device health pings for an archive job.
    try:
        intervals = detector.run(
            fps=cfg['source_fps'], cpu_h264=(cfg['encoder'] == 'cpu-h264'),
            orin=(cfg['encoder'] == 'opencv'), rotate_90=cfg['rotate_90'],
            frame_width=cfg.get('frame_width', 1280), frame_height=cfg.get('frame_height', 720),
            algo=cfg['algo'], min_contour_area=cfg['min_contour_area'],
            motion_trigger_seconds=cfg['motion_trigger_seconds'],
            warmup_seconds=cfg['warmup_seconds'], bitrate=cfg['bitrate'],
        )[media.name]
        detector._raise_if_video_saver_failed()
        if loader.processed_frames != expected_frames:
            raise RuntimeError(f'Input ended early: decoded {loader.processed_frames}/{expected_frames} frames')
        clips = sorted((out / md.MOTION_VIDS).glob('*.mp4'))
        if len(clips) != len(intervals):
            raise RuntimeError(f'Expected {len(intervals)} clips, found {len(clips)}')
        start = datetime.fromisoformat(job['folder_start'])
        for clip, (first, last) in zip(clips, intervals):
            info = probe(clip)  # Reject incomplete/truncated MP4 containers.
            trigger = start + timedelta(seconds=first / cfg['source_fps'])
            expected_name = f"{job['prefix']}_{trigger:%Y%m%d_%H%M%S}_M.mp4"
            if clip.name != expected_name:
                raise RuntimeError(f'Unexpected timestamp: {clip.name}; expected {expected_name}')
            sidecar = out / md.MOTION_VIDS_METADATA_DIR / f'{clip.stem}.json'
            payload = json.loads(sidecar.read_text())  # Missing metadata is a failed job.
            if int(payload['nb_frames']) != int(info['nb_frames']):
                raise RuntimeError(f'Clip/metadata frame counts disagree: {clip}')
            payload['archive_source'] = {
                **job['source'], 'folder_start': job['folder_start'],
                'folder_time_precision': 'minute', 'recording_timezone': cfg['recording_timezone'],
                'source_fps': cfg['source_fps'], 'motion_trigger_frame': first,
                'motion_end_frame': last, 'motion_trigger_time': trigger.isoformat(),
                'filename_time_basis': 'motion trigger; clip includes earlier pre-roll',
                'rotate_90': cfg['rotate_90'],
                'frame_width': cfg.get('frame_width', 1280),
                'frame_height': cfg.get('frame_height', 720),
            }
            write_json(sidecar, payload)
        write_json(out / 'worker-result.json', {'input_frames': expected_frames,
                   'processed_frames': loader.processed_frames, 'motion_clips': len(clips),
                   'motion_intervals_frames': intervals})
    finally:
        # The detector closes its loader. Queues are owned here and must not leak
        # across jobs. Abrupt reader failures are bounded by the parent timeout.
        for q in (detector.status_q, detector.result_q):
            q.close()
            q.join_thread()


def positive_int(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_root', type=Path, help='Contains YYYYMMDD/HHMM/*.h264')
    parser.add_argument('output_root', type=Path, help='Writable result/work/log directory')
    parser.add_argument('--source-fps', required=True, type=positive_int,
                        help='Original integer recording FPS; all frames are processed at this rate')
    parser.add_argument('--device-id', required=True, help='Filename prefix, e.g. HIRMD-koeye-pi-0')
    parser.add_argument('--frame-width', type=positive_int, default=1280, help='Processing/output width after rotation (even)')
    parser.add_argument('--frame-height', type=positive_int, default=720, help='Processing/output height after rotation (even)')
    parser.add_argument('--rotate-90', choices=['cw', 'ccw'])
    parser.add_argument('--encoder', choices=['cpu-h264', 'opencv'], default='cpu-h264',
                        help='cpu-h264 uses GStreamer x264; opencv uses the existing avc1 writer')
    parser.add_argument('--algo', choices=['MOG2', 'CNT'], default='MOG2')
    parser.add_argument('--min-contour-area', type=positive_int, default=5000)
    parser.add_argument('--motion-trigger-seconds', type=float, default=.4)
    parser.add_argument('--warmup-seconds', type=float, default=1)
    parser.add_argument('--bitrate', type=positive_int, default=3000)
    parser.add_argument('--recording-timezone', default='unspecified',
                        help='Provenance label only; folder clock values are never converted')
    parser.add_argument('--limit', type=positive_int, help='Select first N chronological inputs, including completed ones')
    parser.add_argument('--job-timeout', type=positive_int, default=21600,
                        help='Seconds allowed for each remux/worker (default: 6 hours)')
    parser.add_argument('--dry-run', action='store_true', help='List selected sources and timestamps; write nothing')
    args = parser.parse_args(argv)
    if args.frame_width % 2 or args.frame_height % 2:
        parser.error("--frame-width and --frame-height must be positive even integers")
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.device_id):
        parser.error('--device-id must contain only letters, digits, underscores, or hyphens')
    if not math.isfinite(args.motion_trigger_seconds) or args.motion_trigger_seconds <= 0:
        parser.error('--motion-trigger-seconds must be finite and > 0')
    if not math.isfinite(args.warmup_seconds) or args.warmup_seconds < 0:
        parser.error('--warmup-seconds must be finite and >= 0')
    return args


def main(argv=None):
    args = parse_args(argv)
    root, output = args.input_root.resolve(), args.output_root.resolve()
    if not root.is_dir():
        raise ValueError(f'Input directory does not exist: {root}')
    if root == output:
        raise ValueError('Input and output directories must be different')
    if root in output.parents and re.fullmatch(r'\d{8}|\d{4}', output.relative_to(root).parts[0]):
        raise ValueError('Use a non-date output folder, such as archive/motion-results')
    sources = discover(root)
    if args.limit:
        sources = sources[:args.limit]
    if not sources:
        raise ValueError('No YYYYMMDD/HHMM/*.h264 inputs found')
    settings = {key: getattr(args, key) for key in ('source_fps', 'device_id', 'rotate_90', 'frame_width', 'frame_height',
                'encoder', 'algo', 'min_contour_area', 'motion_trigger_seconds',
                'warmup_seconds', 'bitrate', 'recording_timezone')}
    if args.dry_run:
        for source in sources:
            print(f'{folder_timestamp(source).isoformat()}  {source.relative_to(root)}')
        print(f'{len(sources)} input(s); source FPS={args.source_fps}; no files written')
        return 0
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            raise RuntimeError(f'Required executable not found: {tool}')
    output.mkdir(parents=True, exist_ok=True)
    failed = processed = skipped = 0
    with output_lock(output):
        for source in sources:
            try:
                result = process_source(source, root, output, settings, args.job_timeout)
                processed += result == 'processed'
                skipped += result == 'skipped'
            except Exception:
                failed += 1
                LOG.exception('FAILED %s; source unchanged; continuing', source)
    LOG.info('Finished: processed=%d skipped=%d failed=%d', processed, skipped, failed)
    return 1 if failed else 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if len(sys.argv) > 1 and sys.argv[1] == '_worker':
        worker(sys.argv[2])
    else:
        sys.exit(main())
