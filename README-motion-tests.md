# Motion-detection pytest suite

## Layout

```text
salmon-computer-vision/
├── pytest-motion.ini
├── requirements-motion-tests.txt
├── README-motion-tests.md
└── tests/motion_detection/
    ├── conftest.py
    ├── test_coordinator.py
    ├── test_compositor.py
    ├── test_detector_and_saver.py
    ├── test_videoloader.py
    ├── test_utils.py
    ├── test_cli.py
    ├── test_smoke.py
    └── test_known_regressions.py
```

The tests import your checkout from `training/pysalmcount` and load the CLI from `training/tools/run_motion_detect_rtsp.py`. They do not require an editable package installation. Keep your real `pysalmcount/__init__.py`.

## Run on a development machine

From the repository root, in a separate environment:

```bash
python3 -m venv .venv-motion-tests
source .venv-motion-tests/bin/activate
python -m pip install -r requirements-motion-tests.txt
python -m pip install 'opencv-python-headless==4.11.0.86'
python -m pytest -c pytest-motion.ini
```

The real-media smoke tests also require the `ffmpeg` and `ffprobe` executables and FFmpeg's `libx264` encoder. On Ubuntu/Debian, install them with `sudo apt-get install ffmpeg`. Those tests explicitly skip if the required executables or encoder are absent; unit tests still run. OpenCV itself is required for collection and is not silently mocked or skipped.

Run only deterministic unit/regression tests:

```bash
python -m pytest -c pytest-motion.ini -m 'not smoke'
```

Run the local integration smoke tests:

```bash
python -m pytest -c pytest-motion.ini -m 'smoke and not hardware'
```

Generate a coverage report:

```bash
python -m pytest -c pytest-motion.ini \
  --cov=pysalmcount --cov-report=term-missing --cov-report=html:htmlcov-motion
```

The report measures imported `pysalmcount` modules; the separately loaded CLI is tested but is outside that coverage target. No arbitrary coverage threshold is enforced. In a full checkout, other imported package modules may change the denominator.

If tests live outside the checkout, set `SALMON_REPO_ROOT=/absolute/path/to/salmon-computer-vision`. This override also lets CI select an explicit checkout.

## Run on a Pi or Jetson / inside its image

Use the same Python interpreter and OpenCV build as the deployed application. Install only the test runners into a disposable test container or a virtual environment with access to system packages:

```bash
python3 -m pip install 'pytest>=7,<9' 'pytest-cov>=4,<6' 'pytest-timeout>=2,<3'
python3 -m pytest -c pytest-motion.ini
SALMON_TEST_HARDWARE=1 python3 -m pytest -c pytest-motion.ini -m hardware
```

Do not install the headless OpenCV wheel over the deployment's OpenCV build: the opt-in test needs its GStreamer support. The hardware-marked test writes ten synthetic frames using the application's CPU H.264 GStreamer pipeline, then probes the resulting MP4. Once opted in, missing GStreamer support, encoder failure, or incorrect output is a failure, not a skip.

To test an existing image without starting the deployed Compose services:

```bash
docker run --rm --entrypoint bash \
  -v "$PWD:/tools" -w /tools YOUR_SALMONMD_IMAGE \
  -lc "python3 -m pip install 'pytest>=7,<9' 'pytest-cov>=4,<6' 'pytest-timeout>=2,<3' && python3 -m pytest -c pytest-motion.ini"
```

Add `-e SALMON_TEST_HARDWARE=1` and select `-m hardware` to exercise its CPU GStreamer writer. No camera device mounts, RTSP credentials, production disks, privileged mode, or running Compose services are needed for these tests. This does not exercise the Pi/Jetson hardware-accelerated encoder branches.

## What is covered

| Area | Important assertions |
| --- | --- |
| Event coordinator | Concurrent mint/join, one-shot fan-out, shared identity, cross-camera motion refresh, rollover boundaries, finalize precedence, rejoin protection, cleanup, completion barrier, duplicate reports, timeout and forced flushing |
| Compositor | End-aligned leading trims, missing-camera black rows, invalid probes, collision preservation, metadata publication, source retention on encoder/probe/metadata failure, stale-file recovery, conflicting identities, worker continuation |
| Video saver | Lazy shared-buffer attachment, wraparound and frame copies, ordered pre-roll drain, writer-open errors, timestamp calculation, collision preservation, sonar metadata, composite completion reports |
| Detector | Parameter validation, actual OpenCV contour-area boundaries, ring capacity, writable-directory checks, output-growth timeout, saver failure propagation, bounded saver termination, completion forwarding, short run-loop trigger/EOF behavior |
| Video loader | Drop-oldest live queue, file downsampling, live wall-clock sampling and stall recovery, EOF sentinel, network timeouts and old-binding fallback, source classification, live FPS fallback, file decoding and release |
| CLI and helpers | Camera arguments, unsafe/duplicate names, pipeline selection, URL files, device naming, shutdown fan-out, compositor flushing, metadata parsing, health-check cadence and request errors |
| Local smoke tests | Actual FFmpeg encode/composite/probe, decoded top/bottom colors and black placeholders, actual threaded file loading, CLI `--help`, detector loop with deterministic foreground masks |

All generated media and sidecars use pytest temporary directories. HTTP requests are blocked in the test process; background health pings are stubbed for detector-loop tests. Camera/network capture construction is mocked in unit tests. A 30-second per-test timeout bounds unexpected hangs. The deadlock regression test has its own eight-second subprocess timeout, which kills and reaps the child.