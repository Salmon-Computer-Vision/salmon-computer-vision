from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.metadata.index import build_video_metadata_index, write_video_metadata_index


def main() -> None:
    p = argparse.ArgumentParser(description="Build per-video metadata index from Label Studio task JSONs.")
    p.add_argument("--json-dir", required=True)
    p.add_argument("--out-csv", required=True)
    args = p.parse_args()

    rows = build_video_metadata_index(Path(args.json_dir))
    write_video_metadata_index(rows, Path(args.out_csv))

    print(f"Done. indexed_videos={len(rows)} out={args.out_csv}")
