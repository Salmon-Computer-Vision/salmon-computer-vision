from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.negatives.conditions import create_condition_negative_shards


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create condition-balanced negative YOLO label shards from water-conditions CSVs")
    p.add_argument("--conditions-csv", nargs="+", required=True, help="One or more water-conditions CSV files")
    p.add_argument("--out-dir", required=True, help="Output directory for negative shards and manifests")
    p.add_argument("--bucket", default="prod-salmonvision-edge-assets-labelstudio-source")
    p.add_argument("--frames-per-video", type=int, default=5)
    p.add_argument("--frame-stride", type=int, default=3)
    p.add_argument("--frame-offset-mode", choices=["fixed", "video_hash"], default="video_hash")
    p.add_argument("--frame-offset", type=int, default=0)
    p.add_argument("--shard-size", type=int, default=100000)
    p.add_argument("--negative-seed", type=int, default=42)
    p.add_argument("--result-type", default="videorectangle")
    p.add_argument("--from-name", default=None)
    p.add_argument("--to-name", default=None)
    p.add_argument("--aws-profile", default=None)
    p.add_argument("--cache-task-json-dir", default=None)
    return p


def main() -> None:
    args = build_parser().parse_args()

    summary = create_condition_negative_shards(
        csv_paths=[Path(p) for p in args.conditions_csv],
        out_dir=Path(args.out_dir),
        bucket=args.bucket,
        frames_per_video=args.frames_per_video,
        frame_stride=args.frame_stride,
        frame_offset_mode=args.frame_offset_mode,
        frame_offset=args.frame_offset,
        shard_size=args.shard_size,
        negative_seed=args.negative_seed,
        result_type=args.result_type,
        from_name=args.from_name,
        to_name=args.to_name,
        aws_profile=args.aws_profile,
        cache_task_json_dir=Path(args.cache_task_json_dir) if args.cache_task_json_dir else None,
    )

    print(
        f"Done. input_rows={summary['input_rows']} "
        f"selected_videos={summary['written_videos']} "
        f"written_negative_frames={summary['written_negative_frames']} "
        f"failures={len(summary['failures'])}"
    )
