from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.frames.extractor import extract_split_dataset_images


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download source videos and extract only split-requested frames.")
    p.add_argument("--splits-dir", required=True, help="Directory containing train.txt / val.txt / test.txt")
    p.add_argument("--images-root", required=True, help="Output images root")
    p.add_argument("--temp-video-dir", required=True, help="Temporary directory for downloaded videos")
    p.add_argument("--bucket", required=True, help="S3 bucket where videos are kept")
    p.add_argument("--metadata-csv", required=True, help="Metadata CSV of videos especially FPS")
    p.add_argument("--image-ext", default=".jpg", choices=[".jpg", ".png"])
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--keep-videos", action="store_true")
    p.add_argument("--manifest-csv", default=None)
    p.add_argument("--splits", nargs="*", default=["train", "val", "test"])
    return p


def main() -> None:
    args = build_parser().parse_args()

    stats = extract_split_dataset_images(
        splits_dir=Path(args.splits_dir),
        images_root=Path(args.images_root),
        temp_video_dir=Path(args.temp_video_dir),
        bucket=args.bucket,
        metadata_csv=args.metadata_csv,
        image_ext=args.image_ext,
        overwrite=args.overwrite,
        cleanup_video=not args.keep_videos,
        split_names=args.splits,
        manifest_csv=Path(args.manifest_csv) if args.manifest_csv else None,
    )

    print(
        f"Done. splits_seen={stats.splits_seen} "
        f"videos_seen={stats.videos_seen} "
        f"videos_processed={stats.videos_processed} "
        f"videos_failed={stats.videos_failed} "
        f"frames_requested={stats.frames_requested} "
        f"frames_written={stats.frames_written}"
    )
