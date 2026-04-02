from __future__ import annotations

import argparse
from pathlib import Path
import yaml

from object_detection.frames.extractor import pack_split_dataset_shards


def load_class_names_from_yolo_yaml(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    names = data.get("names")
    if isinstance(names, dict):
        return [names[k] for k in sorted(names, key=lambda x: int(x))]
    if isinstance(names, list):
        return names
    raise ValueError(f"Unsupported names format in {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pack split-aware YOLO dataset into tar shards.")
    p.add_argument("--splits-dir", required=True, help="Directory containing train.txt / val.txt / test.txt")
    p.add_argument("--labels-root", required=True, help="Root of unpacked label files referenced by split manifests")
    p.add_argument("--shards-root", required=True, help="Output directory for packed tar shards")
    p.add_argument("--manifests-root", required=True, help="Output directory for new image manifests + data.yaml")
    p.add_argument("--temp-video-dir", required=True, help="Temporary directory for downloaded videos")
    p.add_argument("--metadata-csv", nargs="+", required=True,
                   help="One or more metadata CSVs with columns including video_stem,fps,s3_key")
    p.add_argument("--data-yaml", required=True, help="YOLO data.yaml used only to get class names")
    p.add_argument("--bucket", default="prod-salmonvision-edge-assets-labelstudio-source",
                   help="Fallback bucket if metadata row lacks s3_key")
    p.add_argument("--image-ext", default=".jpg", choices=[".jpg", ".png"])
    p.add_argument("--keep-videos", action="store_true")
    p.add_argument("--manifest-csv", default=None)
    p.add_argument("--splits", nargs="*", default=["train", "val", "test"])
    p.add_argument("--shard-size", type=int, default=100000)
    return p


def main() -> None:
    args = build_parser().parse_args()
    class_names = load_class_names_from_yolo_yaml(Path(args.data_yaml))

    stats = pack_split_dataset_shards(
        splits_dir=Path(args.splits_dir),
        labels_root=Path(args.labels_root),
        shards_root=Path(args.shards_root),
        manifests_root=Path(args.manifests_root),
        temp_video_dir=Path(args.temp_video_dir),
        metadata_csv_paths=[Path(p) for p in args.metadata_csv],
        class_names=class_names,
        bucket=args.bucket,
        image_ext=args.image_ext,
        cleanup_video=not args.keep_videos,
        split_names=args.splits,
        manifest_csv=Path(args.manifest_csv) if args.manifest_csv else None,
        shard_size=args.shard_size,
    )

    print(
        f"Done. splits_seen={stats.splits_seen} "
        f"videos_seen={stats.videos_seen} "
        f"videos_processed={stats.videos_processed} "
        f"videos_failed={stats.videos_failed} "
        f"frames_requested={stats.frames_requested} "
        f"images_written={stats.images_written} "
        f"labels_written={stats.labels_written}"
    )
