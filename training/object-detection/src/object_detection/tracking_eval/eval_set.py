from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".avi", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABEL_EXTS = {".txt"}
VALID_SPLITS = {"val", "test"}

# Example:
#   HIRMD-tankeeah-jetson-0_20250714_012827_M
#   ODFW-sodasprings-jetson-0_20240108_000000_M
VIDEO_STEM_RE = re.compile(
    r"(?P<stem>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+_\d{8}_\d{6}_[MC])"
)


@dataclass(frozen=True)
class ParsedVideoStem:
    video_stem: str
    org: str
    site: str
    device: str
    date: str
    time: str
    clip_type: str


@dataclass(frozen=True)
class VideoRecord:
    split: str
    video_stem: str
    org: str
    site: str
    device: str
    date: str
    time: str
    clip_type: str
    n_manifest_frames: int
    first_manifest_path: str
    metadata_found: bool
    source_video_filename: str
    s3_key: str
    s3_uri: str
    local_video_path: str


def parse_video_stem(video_stem: str) -> ParsedVideoStem:
    """
    Parse normalized SalmonVision video stem:

      ORG-site-device_YYYYMMDD_HHMMSS_M

    Device IDs commonly contain a hyphen, e.g. jetson-0, jetsonnx-1,
    jetsonorin-0, pi-0. This fallback parser assumes the device is the final
    two dash-separated tokens when the last token is numeric.
    """
    stem = Path(video_stem).stem

    m = re.match(
        r"^(?P<prefix>.+)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<clip_type>[MC])$",
        stem,
    )
    if not m:
        raise ValueError(f"Could not parse normalized video stem: {video_stem!r}")

    prefix = m.group("prefix")
    parts = prefix.split("-")
    if len(parts) < 3:
        raise ValueError(f"Could not parse org/site/device from stem: {video_stem!r}")

    org = parts[0]

    if len(parts) >= 4 and parts[-1].isdigit():
        device = "-".join(parts[-2:])
        site = "-".join(parts[1:-2])
    else:
        device = parts[-1]
        site = "-".join(parts[1:-1])

    if not site:
        raise ValueError(f"Parsed empty site from stem: {video_stem!r}")

    return ParsedVideoStem(
        video_stem=stem,
        org=org,
        site=site,
        device=device,
        date=m.group("date"),
        time=m.group("time"),
        clip_type=m.group("clip_type"),
    )


def _strip_manifest_line(line: str) -> str:
    """Keep the first whitespace-separated token from a manifest line."""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    return line.split()[0]


def extract_video_stem_from_manifest_path(line: str) -> Optional[str]:
    """
    Extract a normalized video stem from a manifest row.

    Common inputs are frame/image manifests such as:
      /abs/path/test/<video_stem>/frame_000123.jpg
      test/<video_stem>/frame_000123.jpg

    Direct video paths and label paths are also accepted.
    """
    token = _strip_manifest_line(line)
    if not token:
        return None

    p = Path(token)

    if p.suffix.lower() in VIDEO_EXTS:
        candidate = p.stem
        if VIDEO_STEM_RE.fullmatch(candidate):
            return candidate

    if p.suffix.lower() in IMAGE_EXTS.union(LABEL_EXTS):
        parent = p.parent.name
        if VIDEO_STEM_RE.fullmatch(parent):
            return parent

    for part in reversed(p.parts):
        candidate = Path(part).stem
        if VIDEO_STEM_RE.fullmatch(candidate):
            return candidate

    m = VIDEO_STEM_RE.search(token)
    if m:
        return m.group("stem")

    return None


def read_eval_manifest(manifest: Path) -> Tuple[Counter, Dict[str, str]]:
    """
    Return:
      - Counter(video_stem -> number of selected manifest rows)
      - first manifest path seen for each video_stem

    The frame count is descriptive only. Tracking GT will later be generated
    from the continuous Label Studio video trajectories, not from these sampled
    detector-training frames.
    """
    counts: Counter = Counter()
    first_path: Dict[str, str] = {}

    with manifest.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            token = _strip_manifest_line(line)
            if not token:
                continue

            stem = extract_video_stem_from_manifest_path(token)
            if stem is None:
                print(
                    f"[WARN] Could not extract video stem from manifest line "
                    f"{line_no}: {token}",
                    file=sys.stderr,
                )
                continue

            counts[stem] += 1
            first_path.setdefault(stem, token)

    return counts, first_path


def _parse_compare_manifest(value: str) -> Tuple[str, Path]:
    """Parse --compare-manifest NAME=PATH."""
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "--compare-manifest must be NAME=PATH, e.g. train=data/.../train.txt"
        )

    name, raw_path = value.split("=", 1)
    name = name.strip()
    raw_path = raw_path.strip()

    if not name or not raw_path:
        raise argparse.ArgumentTypeError(
            "--compare-manifest must contain both a name and path"
        )

    return name, Path(raw_path)


def assert_no_video_overlap(
    *,
    split: str,
    selected_video_stems: Sequence[str],
    compare_manifests: Sequence[Tuple[str, Path]],
) -> None:
    """Fail if any selected video also appears in a comparison manifest."""
    selected = set(selected_video_stems)
    if not selected:
        return

    problems: List[str] = []

    for compare_name, compare_path in compare_manifests:
        # Allow callers/DVC foreach stages to pass train/val/test uniformly.
        # The current split is not a leakage comparison against itself.
        if compare_name.strip().lower() == split.strip().lower():
            continue

        compare_counts, _ = read_eval_manifest(compare_path)
        overlap = sorted(selected.intersection(compare_counts.keys()))
        if not overlap:
            continue

        preview = ", ".join(overlap[:10])
        suffix = "" if len(overlap) <= 10 else f", ... (+{len(overlap) - 10} more)"
        problems.append(
            f"{split} overlaps {compare_name} in {len(overlap)} video(s): "
            f"{preview}{suffix}"
        )

    if problems:
        raise RuntimeError("Tracking split leakage detected:\n  - " + "\n  - ".join(problems))


def _nonempty(row: Dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _basename_stem(value: str) -> str:
    if not value:
        return ""
    value = value.strip().rstrip("/")
    return Path(value.split("/")[-1]).stem


def _looks_like_video_ref(value: str) -> bool:
    if not value:
        return False
    suffix = Path(value.split("?")[0]).suffix.lower()
    return suffix in VIDEO_EXTS


def _index_metadata_rows(metadata_csv: Path) -> Dict[str, Dict[str, str]]:
    """
    Build video_stem -> metadata row.

    This intentionally tolerates schema drift by indexing common explicit
    columns plus any value that looks like a video reference.
    """
    if not metadata_csv.exists():
        raise FileNotFoundError(f"metadata CSV does not exist: {metadata_csv}")

    index: Dict[str, Dict[str, str]] = {}
    duplicates: Counter = Counter()

    with metadata_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"metadata CSV has no header: {metadata_csv}")

        for row in reader:
            candidate_values: List[str] = []

            for col in [
                "video_stem",
                "stem",
                "filename_stem",
                "video_filename",
                "filename",
                "metadata_file_filename",
                "file_name",
                "basename",
                "video_path",
                "path",
                "s3_key",
                "s3_uri",
                "video_uri",
                "source_uri",
                "source_video_uri",
            ]:
                value = row.get(col)
                if value:
                    candidate_values.append(value)

            for value in row.values():
                if value and _looks_like_video_ref(str(value)):
                    candidate_values.append(str(value))

            for value in candidate_values:
                stem = _basename_stem(value)
                if not stem or not VIDEO_STEM_RE.fullmatch(stem):
                    continue

                if stem in index:
                    duplicates[stem] += 1
                    continue
                index[stem] = row

    if duplicates:
        print(
            f"[WARN] Metadata had duplicate rows for {len(duplicates)} stems; "
            f"kept first occurrence.",
            file=sys.stderr,
        )

    return index


def _metadata_source_filename(row: Dict[str, str], video_stem: str) -> str:
    value = _nonempty(
        row,
        "video_filename",
        "filename",
        "metadata_file_filename",
        "file_name",
        "basename",
    )
    if value:
        return Path(value).name

    for col in [
        "s3_key",
        "s3_uri",
        "video_uri",
        "source_uri",
        "source_video_uri",
        "video_path",
        "path",
    ]:
        value = row.get(col)
        if value and _looks_like_video_ref(str(value)):
            return Path(str(value).rstrip("/").split("/")[-1]).name

    return f"{video_stem}.mp4"


def _metadata_s3_key(row: Dict[str, str]) -> str:
    value = _nonempty(row, "s3_key", "key", "object_key")
    if value:
        if value.startswith("s3://"):
            return value.replace("s3://", "", 1).split("/", 1)[-1]
        return value

    for col in ["s3_uri", "video_uri", "source_uri", "source_video_uri"]:
        value = row.get(col)
        if value and str(value).startswith("s3://"):
            no_scheme = str(value)[len("s3://") :]
            parts = no_scheme.split("/", 1)
            if len(parts) == 2:
                return parts[1]

    return ""


def _metadata_s3_uri(row: Dict[str, str]) -> str:
    value = _nonempty(row, "s3_uri", "video_uri", "source_uri", "source_video_uri")
    if value.startswith("s3://"):
        return value
    return ""


def _derive_default_s3_key(parsed: ParsedVideoStem) -> str:
    filename = f"{parsed.video_stem}.mp4"
    return f"{parsed.org}/{parsed.site}/{parsed.device}/motion_vids/{filename}"


def _get_site_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "site", "site_name", "metadata_file_site_reference_string")


def _get_org_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "org", "orgid", "org_id", "project", "Project")


def _get_device_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "device", "device_id", "camera", "Camera")


def make_tracking_eval_set(
    *,
    manifest: Path,
    split: str,
    metadata_csv: Path,
    out_csv: Path,
    videos_dir: Path,
    max_videos: int = 0,
    require_metadata: bool = False,
    compare_manifests: Sequence[Tuple[str, Path]] = (),
) -> List[VideoRecord]:
    """
    Build a deterministic one-row-per-video evaluation index for val or test.

    The input YOLO manifest is used only to decide which source videos belong
    to the evaluation split. This function does not download videos and does
    not construct tracking ground truth.
    """
    split = str(split).strip().lower()
    if split not in VALID_SPLITS:
        raise ValueError(
            f"split must be one of {sorted(VALID_SPLITS)}, got: {split!r}"
        )
    if max_videos < 0:
        raise ValueError(f"max_videos must be >= 0, got: {max_videos}")

    frame_counts, first_paths = read_eval_manifest(manifest)
    if not frame_counts:
        raise RuntimeError(f"No video stems found in {split} manifest: {manifest}")

    # Check the complete split before applying any debugging subset.
    assert_no_video_overlap(
        split=split,
        selected_video_stems=tuple(frame_counts.keys()),
        compare_manifests=compare_manifests,
    )

    metadata_index = _index_metadata_rows(metadata_csv)
    records: List[VideoRecord] = []
    missing_metadata: List[str] = []

    for video_stem in sorted(frame_counts.keys()):
        parsed = parse_video_stem(video_stem)
        row = metadata_index.get(video_stem)

        metadata_found = row is not None
        if row is None:
            missing_metadata.append(video_stem)
            row = {}

        org = _get_org_from_metadata(row) or parsed.org
        site = _get_site_from_metadata(row) or parsed.site
        device = _get_device_from_metadata(row) or parsed.device

        source_video_filename = _metadata_source_filename(row, video_stem)
        s3_uri = _metadata_s3_uri(row)
        s3_key = _metadata_s3_key(row)
        if not s3_key:
            s3_key = _derive_default_s3_key(parsed)

        # This is only a future materialization target. No download occurs here.
        local_video_path = str(videos_dir / split / f"{video_stem}.mp4")

        records.append(
            VideoRecord(
                split=split,
                video_stem=video_stem,
                org=org,
                site=site,
                device=device,
                date=parsed.date,
                time=parsed.time,
                clip_type=parsed.clip_type,
                n_manifest_frames=int(frame_counts[video_stem]),
                first_manifest_path=first_paths[video_stem],
                metadata_found=metadata_found,
                source_video_filename=source_video_filename,
                s3_key=s3_key,
                s3_uri=s3_uri,
                local_video_path=local_video_path,
            )
        )

    if missing_metadata:
        msg = (
            f"[WARN] Missing metadata rows for {len(missing_metadata)} / "
            f"{len(frame_counts)} {split} videos. Using fallback S3 keys for those videos."
        )
        if require_metadata:
            preview = "\n".join(f"  - {x}" for x in missing_metadata[:20])
            raise RuntimeError(msg + "\n" + preview)
        print(msg, file=sys.stderr)

    records.sort(key=lambda r: (r.site, r.date, r.time, r.device, r.video_stem))

    if max_videos > 0:
        records = records[:max_videos]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    (videos_dir / split).mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "split",
        "video_stem",
        "org",
        "site",
        "device",
        "date",
        "time",
        "clip_type",
        "n_manifest_frames",
        "first_manifest_path",
        "metadata_found",
        "source_video_filename",
        "s3_key",
        "s3_uri",
        "local_video_path",
    ]

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "split": r.split,
                    "video_stem": r.video_stem,
                    "org": r.org,
                    "site": r.site,
                    "device": r.device,
                    "date": r.date,
                    "time": r.time,
                    "clip_type": r.clip_type,
                    "n_manifest_frames": r.n_manifest_frames,
                    "first_manifest_path": r.first_manifest_path,
                    "metadata_found": str(r.metadata_found).lower(),
                    "source_video_filename": r.source_video_filename,
                    "s3_key": r.s3_key,
                    "s3_uri": r.s3_uri,
                    "local_video_path": r.local_video_path,
                }
            )

    return records



# Backwards-compatible Python API aliases. New code should use the eval names.
def read_test_manifest(test_manifest: Path) -> Tuple[Counter, Dict[str, str]]:
    return read_eval_manifest(test_manifest)


def make_tracking_test_set(
    *,
    test_manifest: Path,
    metadata_csv: Path,
    out_csv: Path,
    videos_dir: Path,
    max_videos: int = 0,
    require_metadata: bool = False,
) -> List[VideoRecord]:
    return make_tracking_eval_set(
        manifest=test_manifest,
        split="test",
        metadata_csv=metadata_csv,
        out_csv=out_csv,
        videos_dir=videos_dir,
        max_videos=max_videos,
        require_metadata=require_metadata,
    )

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build a one-row-per-video tracking evaluation CSV from a YOLO "
            "validation or test manifest. This stage selects videos only; it "
            "does not download MP4s or generate tracking GT."
        )
    )
    manifest_group = p.add_mutually_exclusive_group(required=True)
    manifest_group.add_argument("--manifest", type=Path)
    manifest_group.add_argument(
        "--test-manifest",
        type=Path,
        help=(
            "Deprecated compatibility alias for --manifest PATH --split test."
        ),
    )
    p.add_argument("--split", choices=sorted(VALID_SPLITS))
    p.add_argument("--metadata-csv", required=True, type=Path)
    p.add_argument("--out-csv", required=True, type=Path)
    p.add_argument(
        "--videos-dir",
        required=True,
        type=Path,
        help="Root for future video materialization; rows use <root>/<split>/<video>.mp4.",
    )
    p.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="Deterministic debug subset after leakage checks. 0 means all videos.",
    )
    p.add_argument(
        "--require-metadata",
        action="store_true",
        help="Fail if any selected video stem is missing from the metadata CSV.",
    )
    p.add_argument(
        "--compare-manifest",
        action="append",
        type=_parse_compare_manifest,
        default=[],
        metavar="NAME=PATH",
        help=(
            "Optional manifest to check for video-level split leakage. May be "
            "specified multiple times, e.g. --compare-manifest train=.../train.txt."
        ),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_argparser()
    args = parser.parse_args(argv)

    manifest = args.manifest
    split = args.split

    if args.test_manifest is not None:
        manifest = args.test_manifest
        if split is not None and split != "test":
            parser.error("--test-manifest may only be used with --split test")
        split = "test"

    if manifest is None:
        parser.error("one of --manifest or --test-manifest is required")
    if split is None:
        parser.error("--split is required when using --manifest")

    records = make_tracking_eval_set(
        manifest=manifest,
        split=split,
        metadata_csv=args.metadata_csv,
        out_csv=args.out_csv,
        videos_dir=args.videos_dir,
        max_videos=args.max_videos,
        require_metadata=args.require_metadata,
        compare_manifests=args.compare_manifest,
    )

    by_site = Counter(r.site for r in records)

    print(f"Wrote {len(records)} tracking-{split} videos to: {args.out_csv}")
    print("Videos by site:")
    for site, count in sorted(by_site.items()):
        print(f"  {site}: {count}")


if __name__ == "__main__":
    main()
