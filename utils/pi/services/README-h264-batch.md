# Batch motion extraction from the H.264 archive

This package adds a batch runner and a separate Compose service. It requires the previously updated motion-detection package, including the two bug fixes and `rotate_90`. **No existing production files need replacing.** Extract the ZIP at the root of `salmon-computer-vision`.

New files:

- `training/tools/batch_motion_h264.py`
- `utils/pi/services/docker-compose-h264-batch.yml`
- `utils/pi/services/h264-batch.env.example`
- `tests/motion_detection/test_batch_h264.py`
- This guide and the test results.

## What it does

For each source, in recording-time order:

1. Find `YYYYMMDD/HHMM/*.h264`, including nested date folders. Ignore Windows system/recycle trees, `.index` files, and symlinks.
2. Interpret the nearest date/time pair as the source start, with seconds set to `00`.
3. Remux the raw video into one temporary `input_YYYYMMDD_HHMMSS.mp4` using FFmpeg stream copy. This adds a container and timing without recompressing the video.
4. Start a fresh Python worker that calls your existing `MotionDetector` in file mode, with continuous recording disabled and an explicit historical filename. All original frames are processed; no wall-clock sampling or frame downsampling is used.
5. Validate input frame consumption, motion clip count, output MP4 frame counts, and metadata. Add source provenance to each clip's JSON.
6. Publish that source's result directory and a completion marker only after success. Delete its temporary remux. Keep its diagnostic log.

Only one source/worker runs at a time. Successful jobs are skipped on reruns; failed jobs remain retryable. Output files are never intentionally overwritten. A lock prevents two batch runners from using the same output root.

The provided tree contains **2,070 H.264 files**: 1,995 in the direct layout and 75 inside nested date directories:

- `20260813/20260722/...` (3 files)
- `20260825/20260829/...` (72 files)

These may or may not be duplicate recordings; the tree cannot establish that. They are processed independently. Their full relative paths are preserved under `results/`, so equal timestamps cannot collide across sources. No content deduplication is attempted.

## Timestamp assumptions and limits

The format is **YYYYMMDD**, followed by **HHMM**, not YYYMMDD.

For `/archive/20260720/1400/CH01.h264`, the assumed recording start is `2026-07-20 14:00:00`. A motion trigger 192 seconds into it receives a name such as:

```text
ORG-site-pi-0_CH01_20260720_140312_M.mp4
```

This is the detector's existing **motion-trigger timestamp**, not the exact first encoded frame time: the clip also includes earlier pre-roll (up to approximately two seconds). Fractional seconds are available in the added JSON trigger timestamp; filenames retain their existing one-second precision. Midnight rollover is handled automatically.

Folder clock values are preserved exactly, with **no timezone conversion**. `--recording-timezone America/Vancouver` records a label in metadata only; it does not convert times or resolve daylight-saving ambiguity. Filesystem modification times reflect processing, not historical recording time.

The tree alone cannot verify whether `HHMM` denotes the actual first frame or just a recorder's time bucket. This runner assumes the first frame begins at `HH:MM:00`. If that assumption is false, exact timestamps require the recorder's additional timing information. The proprietary `.index` files are not interpreted.

**You must supply the original recording FPS.** Raw H.264 may not provide reliable timing. The wrong value changes elapsed time and therefore clip timestamps. Obtain it from the original recorder settings or reliable recording metadata. An `ffprobe` value of 25 for a raw stream can be a default, not evidence that the camera recorded at 25 FPS.

This version supports **constant, positive integer FPS**. Fractional/variable-rate recordings require additional timing support; do not round their FPS. All frames are processed to keep `frame_count / fps` aligned with source time. This may be slower than processing at 10 FPS, but the job runs as fast as the hardware permits rather than in real time.

Each file is processed independently. Background warmup starts again for each file, pre-roll cannot reach into the previous source, and events crossing a file boundary are split. Missing intervals in the archive are not filled. Source decode failures or proprietary/nonstandard `.h264` content can still require recorder-specific conversion.

## Set up on the Raspberry Pi

Use the same Pi-compatible salmonmd image you normally deploy. It must have FFmpeg/ffprobe, NumPy, requests, ffmpeg-python, and an OpenCV build with **GStreamer** and the x264 writer plugins. The supplied Raspberry Pi Dockerfile already requests the relevant FFmpeg/GStreamer packages; verify the actual image's Python/OpenCV installation.

The default encoder is the existing CPU H.264 GStreamer writer. This avoids assuming that the Pi exposes the Jetson encoder or a particular hardware encoder. Do not install the pip headless OpenCV wheel over the deployment OpenCV build.

If using the existing test suite, its opt-in `test_deployment_gstreamer_cpu_writer` test can verify this encoder inside the image before a long batch. A first archive file with no motion does not exercise the output encoder.

On the Pi, ensure the checkout contains the prior fixes/rotation change plus this new script. The Compose service mounts that checkout read-only at `/tools`, so a code-only update does not require rebuilding the image. The image still supplies dependencies.

From the checkout:

```bash
cd utils/pi/services
cp h264-batch.env.example h264-batch.env
nano h264-batch.env
```

Set all values:

```dotenv
SALMONMD_IMAGE=your-registry/salmonmd:your-pi-tag
SALMON_REPO=/home/sami/salmon-computer-vision
H264_INPUT_ROOT=/media/usb
H264_OUTPUT_ROOT=/media/usb/motion-results
ARCHIVE_DEVICE_ID=ORG-site-pi-0
SOURCE_FPS=10
```

**The `10` above is only an example; replace it with the actual recording FPS.** Likewise, replace the device ID, image, and checkout path.

Create the output directory and check configuration:

```bash
mkdir -p /media/usb/motion-results
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml config
```

The source mount is read-only; `/output` is a separate writable mount. Output may live in a non-date subdirectory of the same drive (as above), or on another disk. It must not equal the source root or sit under an input date directory. The scanner ignores `motion-results`, so it will not re-ingest its own output.

Leave room for the final motion clips plus one temporary remux and the current source's staged clips. An interrupted container can leave directories under `.work`; they are ignored on restart. Old `.work` directories can be removed manually while no batch is running. Completed results live under `results/` and must be retained.

For remote Docker contexts, the bind paths refer to the **Pi/daemon host**, not your laptop. Copy/update the checkout on the Pi first. Prefix commands with `docker --context YOUR_PI_CONTEXT compose ...` if launching from your other machine.

## Dry run and a small trial

`compose run` arguments replace the service's command, so include the input/output paths, FPS, and device ID again. Substitute your actual values for the example `10` and `ORG-site-pi-0` below.

```bash
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml run --rm h264-batch \
  /archive /output --source-fps 10 --device-id ORG-site-pi-0 --dry-run
```

This lists the source times and paths and writes no job files. With the provided layout, expect 2,070 entries if the actual disk matches the tree.

Process only the first source:

```bash
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml run --rm h264-batch \
  /archive /output --source-fps 10 --device-id ORG-site-pi-0 --limit 1
```

`--limit` selects the first N chronological inputs, including already-completed ones. It does not mean "the next N unprocessed files". Inspect the output clips, their timestamps, and the per-source log before committing to the full archive. An empty `motion_vids` directory is valid if the detector found no motion; `complete.json` records a successful zero-clip result.

Optional rotation for a trial:

```bash
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml run --rm h264-batch \
  /archive /output --source-fps 10 --device-id ORG-site-pi-0 \
  --rotate-90 cw --limit 1
```

Use `ccw` for counterclockwise. To use rotation for the full `up` run, add these items to the service's `command` list:

```yaml
      - --rotate-90
      - cw
```

Other supported options include `--min-contour-area`, `--motion-trigger-seconds`, `--warmup-seconds`, `--algo`, `--bitrate`, `--recording-timezone`, and `--job-timeout`. The existing morphology, clip-length, and post-roll defaults remain in effect. `--encoder opencv` selects the existing `avc1` writer for environments where that backend is available.

Use the same processing parameters for the trial and full run if reusing an output directory. Parameters and code participate in the completion signature.

## Process the full archive and resume

After setting the `.env` values and any optional command items:

```bash
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml up -d h264-batch

docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml logs -f h264-batch
```

The job exits when finished (`restart: "no"`). Exit code 0 means all selected inputs completed or were skipped as already complete; 1 means at least one failed. Failed inputs are logged and processing continues. The default timeout is six hours for each source's remux or processing worker; adjust `--job-timeout` for your measured Pi throughput.

Restart with the same command to retry failed/interrupted work and skip completed sources. Completion signatures include the relative source path, file size, modification time, parameters, and pipeline code hash. Output file existence and sizes are checked before skipping. The entire raw input is not hashed; this assumes a static archive. No successful-result marker is written for failed jobs.

If a source, settings, code, or existing result changed, the runner refuses to silently reuse/overwrite that result. Choose a fresh output directory for the changed run, or explicitly move the affected source result aside. Pin the image tag/digest for reproducibility: dependency/image changes alone are not part of the code signature.

Stop a run with:

```bash
docker compose --env-file h264-batch.env \
  -f docker-compose-h264-batch.yml stop h264-batch
```

Run this workload separately from live recording where possible: CPU H.264 encoding and disk I/O compete with the live detector. No GPU runtime, camera device mounts, host networking, or privileged mode are required by this batch Compose service.

## Output example

```text
motion-results/
  results/
    20260720/1400/CH01/
      motion_vids/ORG-site-pi-0_CH01_20260720_140312_M.mp4
      motion_vids_metadata/ORG-site-pi-0_CH01_20260720_140312_M.json
      worker-result.json
      complete.json
    20260825/20260829/0000/CH01/
      ...
  logs/
    20260720/1400/CH01/source-....log
```

Keeping results per input avoids filename collisions and permits safe retries. Downstream collection can recursively search `results/**/motion_vids/*.mp4`. Do not flatten duplicate timestamp/channel filenames without a collision policy.

## Run without Docker

From the repository root, using an interpreter with the deployed OpenCV dependencies:

```bash
python3 training/tools/batch_motion_h264.py \
  /media/usb /media/usb/motion-results \
  --source-fps 10 --device-id ORG-site-pi-0 --limit 1
```

Again, replace the example FPS and identifier with the real ones.