#!/usr/bin/env -S uv run python

"""
make_splits.py

Group-wise stratified-ish split for unpacked YOLO label files.

- Input: unpacked labels directory that looks like:
    <root>/<video_stem>/frame_000123.txt

  where video_stem looks like:
    ORG-site-device-id_YYYYMMDD_HHMMSS_M

- Output:
    out_dir/train.txt
    out_dir/val.txt
    out_dir/test.txt
    out_dir/group_assignments.csv
    out_dir/split_report.json

Split unit: group_id = site + device + date(YYYYMMDD)
Balancing objectives (soft): class counts, time-of-day, density bins, box area bins.
"""

from object_detection.splits.cli import main

if __name__ == "__main__":
    main()
