from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".avi", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABEL_EXTS = {".txt"}

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


@dataclass
class VideoRecord:
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

    # Typical:
    #   HIRMD-tankeeah-jetson-0
    #   GWA-stephenssmolt-jetsonnx-1
    #   ODFW-sodasprings-jetson-0
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
    """
    Keep the first whitespace-separated token.

    This supports plain YOLO manifests and simple files with extra columns.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    return line.split()[0]


def extract_video_stem_from_manifest_path(line: str) -> Optional[str]:
    """
    Extract video stem from a manifest line.

    Expected common layout:
      /abs/path/test/<video_stem>/frame_000123.jpg
      test/<video_stem>/frame_000123.jpg

    Also supports direct video paths or labels.
    """
    token = _strip_manifest_line(line)
    if not token:
        return None

    p = Path(token)

    # If the line is a video path, the video stem is the file stem.
    if p.suffix.lower() in VIDEO_EXTS:
        candidate = p.stem
        if VIDEO_STEM_RE.fullmatch(candidate):
            return candidate

    # If the line is an image/label path, the parent directory is usually
    # the video stem.
    if p.suffix.lower() in IMAGE_EXTS.union(LABEL_EXTS):
        parent = p.parent.name
        if VIDEO_STEM_RE.fullmatch(parent):
            return parent

    # Fallback: search every path component from right to left.
    for part in reversed(p.parts):
        candidate = Path(part).stem
        if VIDEO_STEM_RE.fullmatch(candidate):
            return candidate

    # Last fallback: search the raw string.
    m = VIDEO_STEM_RE.search(token)
    if m:
        return m.group("stem")

    return None


def read_test_manifest(test_manifest: Path) -> Tuple[Counter, Dict[str, str]]:
    """
    Return:
      - Counter video_stem -> number of manifest rows
      - first manifest path per video_stem
    """
    counts: Counter = Counter()
    first_path: Dict[str, str] = {}

    with test_manifest.open("r", encoding="utf-8") as f:
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


def _nonempty(row: Dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _basename_stem(value: str) -> str:
    if not value:
        return ""

    # Handles s3://bucket/path/file.mp4 and normal paths.
    value = value.strip()
    value = value.rstrip("/")
    basename = value.split("/")[-1]
    return Path(basename).stem


def _looks_like_video_ref(value: str) -> bool:
    if not value:
        return False
    suffix = Path(value.split("?")[0]).suffix.lower()
    return suffix in VIDEO_EXTS


def _index_metadata_rows(metadata_csv: Path) -> Dict[str, Dict[str, str]]:
    """
    Build video_stem -> metadata row.

    This is intentionally permissive because metadata CSV schemas tend to
    drift. It indexes rows by common columns and by any column that looks like
    a video filename/path/S3 URI.
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

            # Common explicit stem/filename/path columns.
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

            # Fallback: inspect any value that looks like a video reference.
            for value in row.values():
                if value and _looks_like_video_ref(str(value)):
                    candidate_values.append(str(value))

            for value in candidate_values:
                stem = _basename_stem(value)
                if not stem:
                    continue

                # Only index normalized video stems.
                if VIDEO_STEM_RE.fullmatch(stem):
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

    for col in ["s3_key", "s3_uri", "video_uri", "source_uri", "source_video_uri", "video_path", "path"]:
        value = row.get(col)
        if value and _looks_like_video_ref(str(value)):
            return Path(str(value).rstrip("/").split("/")[-1]).name

    return f"{video_stem}.mp4"


def _metadata_s3_key(row: Dict[str, str]) -> str:
    value = _nonempty(row, "s3_key", "key", "object_key")
    if value:
        return value.replace("s3://", "", 1).split("/", 1)[-1] if value.startswith("s3://") else value

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
    """
    Fallback for normalized SalmonVision source layout.
    """
    filename = f"{parsed.video_stem}.mp4"
    return f"{parsed.org}/{parsed.site}/{parsed.device}/motion_vids/{filename}"


def _get_site_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "site", "site_name", "metadata_file_site_reference_string")


def _get_org_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "org", "orgid", "org_id", "project", "Project")


def _get_device_from_metadata(row: Dict[str, str]) -> str:
    return _nonempty(row, "device", "device_id", "camera", "Camera")


def make_tracking_test_set(
    *,
    test_manifest: Path,
    metadata_csv: Path,
    out_csv: Path,
    videos_dir: Path,
    max_videos: int = 0,
    require_metadata: bool = False,
) -> List[VideoRecord]:
    frame_counts, first_paths = read_test_manifest(test_manifest)
    metadata_index = _index_metadata_rows(metadata_csv)

    if not frame_counts:
        raise RuntimeError(f"No video stems found in test manifest: {test_manifest}")

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
            # Fallback assumes your normalized bucket layout.
            s3_key = _derive_default_s3_key(parsed)

        if not s3_uri:
            # Bucket is intentionally not included here because this CSV should
            # remain bucket-agnostic; the download step can prepend --bucket.
            s3_uri = ""

        local_video_path = str(videos_dir / f"{video_stem}.mp4")

        records.append(
            VideoRecord(
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
            f"{len(frame_counts)} test videos. Using fallback S3 keys for those videos."
        )
        if require_metadata:
            preview = "\n".join(f"  - {x}" for x in missing_metadata[:20])
            raise RuntimeError(msg + "\n" + preview)
        print(msg, file=sys.stderr)

    # Deterministic subset for quick testing.
    records.sort(key=lambda r: (r.site, r.date, r.time, r.device, r.video_stem))

    if max_videos and max_videos > 0:
        records = records[:max_videos]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = [
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


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build one-row-per-video tracking test set CSV from a YOLO test manifest."
    )
    p.add_argument("--test-manifest", required=True, type=Path)
    p.add_argument("--metadata-csv", required=True, type=Path)
    p.add_argument("--out-csv", required=True, type=Path)
    p.add_argument("--videos-dir", required=True, type=Path)
    p.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="Limit number of videos for debugging. 0 means use all videos.",
    )
    p.add_argument(
        "--require-metadata",
        action="store_true",
        help="Fail if any manifest video stem is missing from metadata CSV.",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_argparser().parse_args(argv)

    records = make_tracking_test_set(
        test_manifest=args.test_manifest,
        metadata_csv=args.metadata_csv,
        out_csv=args.out_csv,
        videos_dir=args.videos_dir,
        max_videos=args.max_videos,
        require_metadata=args.require_metadata,
    )

    by_site = Counter(r.site for r in records)

    print(f"Wrote {len(records)} tracking-test videos to: {args.out_csv}")
    print("Videos by site:")
    for site, count in sorted(by_site.items()):
        print(f"  {site}: {count}")


if __name__ == "__main__":
    main()
