`normalize_motion_clips_to_s3.py`

Searches only for "M" labeled motion detected clips to re-encode to H.264 MP4
video clips with 2 minutes max.

```
python3 normalize_motion_clips_to_s3.py \
  --input-root "/media/hdd" \
  --work-dir /tmp/upperclub_reencoded \
  --bucket prod-salmonvision-edge-assets-labelstudio-source \
  --orgid ORGID \
  --site sitename \
  --device jetson-0 \
  --date-order dmy \
  --segment-seconds 120 \
  --collision skip \
  --dry-run
```

Or `uv run python` instead of `python3` if you use `uv`.
