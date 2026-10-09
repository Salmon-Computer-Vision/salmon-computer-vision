import argparse
import re
from pathlib import Path

from object_detection.yolo_ls.converter import YoloConverterLSVideo
from object_detection.yolo_ls.parsing import (
    load_class_map_from_yolo_yaml,
    load_json_paths_from_site_manifest,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Label Studio video JSON to YOLO frame labels")
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help=(
            "JSON file or directory containing Label Studio JSON. "
            "Mutually exclusive with --input-manifest."
        ),
    )
    parser.add_argument(
        "--input-manifest",
        default=None,
        help=(
            "Site-index JSON manifest containing raw_root and files[].path. "
            "Mutually exclusive with positional input."
        ),
    )
    parser.add_argument(
        "--manifest-raw-root",
        default=None,
        help=(
            "Optional override for raw_root stored in --input-manifest. "
            "Useful when raw data is mounted at a different location."
        ),
    )
    parser.add_argument("--data-yaml", required=True, help="Path to YOLO data.yaml (with 'names:' mapping)")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--empty-list", default=None, help="Path to write videos with no boxes")
    parser.add_argument("--pattern", default="*.json", help="Glob when input is a directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing per-video folders")
    parser.add_argument("--from-name", default=None, help="Filter by result.from_name (e.g., 'box')")
    parser.add_argument("--to-name", default=None, help="Filter by result.to_name (e.g., 'video')")
    parser.add_argument("--coord-mode", default="percent", help='Set the coordinates mode: "auto", "percent", "normalized", "pixel"')
    parser.add_argument("--include-sites", nargs="*", default=[], help='Only include videos of these sites')
    parser.add_argument("--out-shards", default=None, help="Directory to write TAR shards (instead of many files)")
    parser.add_argument("--shard-size", type=int, default=10000, help="Number of frame label files per shard")
    parser.add_argument("--frame-stride", type=int, default=1,
                    help="Keep every Nth frame (1 keeps all)")
    parser.add_argument("--frame-offset-mode", choices=["fixed", "video_hash"], default="video_hash",
                        help="How to choose offset within stride")
    parser.add_argument("--frame-offset", type=int, default=0,
                        help="Offset for fixed mode (0..stride-1)")
    parser.add_argument("--include-negatives", action="store_true",
                    help="Add negative frames from videos with no annotations")
    parser.add_argument("--negative-ratio", type=float, default=0.10,
                        help="Max negatives as fraction of final dataset")
    parser.add_argument("--negatives-per-video", type=int, default=6,
                        help="Max sampled negative frames per empty video")
    parser.add_argument("--negative-seed", type=int, default=42,
                        help="Seed for deterministic negative sampling")
    parser.add_argument("--annotated-negative-sites", default="",
                        help="Comma/space-separated sites to sample unlabeled frames from reviewed annotated videos")
    parser.add_argument("--annotated-negatives-per-video", type=int, default=12,
                        help="Max negative frames from each annotated video (before global ratio cap)")
    parser.add_argument("--negative-exclusion-frames", type=int, default=3,
                        help="Exclude frames within this temporal distance of any LS annotation")
    parser.add_argument("--stats-dir", default=None,
                    help="Directory to write site/class frame and box count summaries")

    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.input is None and args.input_manifest is None:
        parser.error(
            "one of positional input or --input-manifest is required"
        )

    if args.input is not None and args.input_manifest is not None:
        parser.error(
            "positional input and --input-manifest are mutually exclusive"
        )

    data_yaml_path = Path(args.data_yaml)
    class_map = load_class_map_from_yolo_yaml(data_yaml_path)

    conv = YoloConverterLSVideo(
        class_map=class_map,
        output_dir=Path(args.out),
        empty_list_path=Path(args.empty_list) if args.empty_list else None,
        overwrite_video_dir=args.overwrite,
        from_name=args.from_name,
        to_name=args.to_name,
        coord_mode=args.coord_mode,
        include_sites=args.include_sites,
        shard_dir=Path(args.out_shards) if args.out_shards else None,
        shard_size=args.shard_size,
        frame_stride=args.frame_stride,
        frame_offset_mode=args.frame_offset_mode,
        frame_offset=args.frame_offset,
        include_negatives=args.include_negatives,
        negative_ratio=args.negative_ratio,
        negatives_per_video=args.negatives_per_video,
        negative_seed=args.negative_seed,
        annotated_negative_sites=[v for v in re.split(r"[\s,]+", args.annotated_negative_sites.strip()) if v],
        annotated_negatives_per_video=args.annotated_negatives_per_video,
        negative_exclusion_frames=args.negative_exclusion_frames,
        stats_dir=Path(args.stats_dir) if args.stats_dir else None,
    )

    if args.input_manifest is not None:
        manifest_path = Path(args.input_manifest)

        json_paths = load_json_paths_from_site_manifest(
            manifest_path,
            raw_root_override=(
                Path(args.manifest_raw_root)
                if args.manifest_raw_root
                else None
            ),
        )

        print(
            f"Converting {len(json_paths)} Label Studio export(s) "
            f"from manifest {manifest_path}"
        )

        s = conv.convert_files(json_paths)

    else:
        inp = Path(args.input)

        if inp.is_dir():
            print(f"Converting labels from directory {inp}")
            s = conv.convert_folder(
                inp,
                pattern=args.pattern,
            )
        else:
            print(f"Converting labels from file {inp}")
            s = conv.convert_file(inp)

    neg_written, max_neg, total_candidate_frames = conv.materialize_negatives()
    s.negative_files_written += neg_written
    s.total_candidate_negative_frames += total_candidate_frames

    conv.export_stats()

    if getattr(conv, "_sharder", None):
        conv._sharder.close()

    print(
        f"Done. with_boxes={s.videos_with_boxes} without_boxes={s.videos_without_boxes} "
        f"positive_label_files={s.label_files_written} "
        f"negative_label_files={s.negative_files_written} "
        f"total_candidate_negative_frames={s.total_candidate_negative_frames} "
        f"max_neg={max_neg} "
        f"negative_from_empty={conv._negative_report.get('selected_from_empty_videos', 0)} "
        f"negative_from_annotated={conv._negative_report.get('selected_from_annotated_videos', 0)} "
        f"errors={s.errors}"
    )
