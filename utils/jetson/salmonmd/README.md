# Jetson SalmonMD

The docker service here will perform motion detection and save continuous and
motion detected videos to a specified folder (likely an external drive) using
the hostname of the device to demarcate folder structure.

Similar instructions to [Raspi's motion detection](../../pi/services).

## Multi-camera motion clips

Set `RTSP_URL` to a comma-separated list of camera URLs and add
`--multi-camera` to `FLAGS`. Use `--cam-names` to assign camera identities; its
order must match `RTSP_URL` and determines the top-to-bottom order in the
composite.

For example:

```dotenv
RTSP_URL=rtsp://192.168.1.88/0,rtsp://192.168.1.89/0,rtsp://192.168.1.90/0
FLAGS=--cpu_h264 --multi-camera --cam-names left,middle,right --url 'https://google.com'
```

Multi-camera motion clips are vertically composited by default. Each camera is
recorded independently into `motion_vids_parts/`, with temporary metadata in
`motion_vids_parts_metadata/`. After every available row for an event part is
combined successfully, the canonical composite is written to `motion_vids/`
(or `motion_vids_staging/` with `--staging`) and the corresponding intermediate
files are removed.

For three 1280x720 rows, the output is a 1280x2160 H.264 MP4 named:

```text
{orgid}-{site}-{device}_{YYYYMMDD_HHMMSS}_M.mp4
```

Only the final file under `motion_vids/` follows the normal cloud sync path;
the intermediate directories are not uploaded. Use `--no-composite` to retain
separate per-camera motion clips instead.
