from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ARCHIVE_CLASSES = ("GLACIER", "DEEP_ARCHIVE")


@dataclass(frozen=True)
class VideoRequest:
    split: str
    video_stem: str
    s3_uri: str
    local_path: Path


@dataclass(frozen=True)
class VideoDownloadResult:
    split: str
    video_stem: str
    s3_uri: str
    local_video_path: str
    status: str
    size_bytes: int
    archive_class: str = ""
    error: str = ""


@dataclass(frozen=True)
class DownloadStats:
    videos_total: int
    existing: int
    downloaded: int
    archived: int
    missing: int
    errors: int
    bytes_present: int


def _clean_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _make_s3_uri(row: Dict[str, str], bucket: str) -> str:
    uri = _clean_text(row.get("s3_uri"))
    if uri.startswith("s3://"):
        return uri

    key = _clean_text(row.get("s3_key"))
    if not key:
        raise ValueError(
            f"Missing both s3_uri and s3_key for video_stem={row.get('video_stem', '')!r}"
        )
    if not bucket:
        raise ValueError(
            f"--bucket is required when s3_uri is absent for video_stem={row.get('video_stem', '')!r}"
        )
    return f"s3://{bucket}/{key.lstrip('/')}"


def read_video_requests(
    eval_csv: Path,
    *,
    bucket: str,
    expected_split: Optional[str] = None,
) -> List[VideoRequest]:
    if not eval_csv.exists():
        raise FileNotFoundError(f"Evaluation CSV does not exist: {eval_csv}")

    requests: List[VideoRequest] = []
    seen_stems = set()
    seen_paths = set()

    with eval_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Evaluation CSV has no header: {eval_csv}")

        required = {"video_stem", "local_video_path"}
        missing_cols = sorted(required.difference(reader.fieldnames))
        if missing_cols:
            raise ValueError(
                f"Evaluation CSV missing required column(s): {', '.join(missing_cols)}"
            )

        for line_no, row in enumerate(reader, start=2):
            stem = _clean_text(row.get("video_stem"))
            local = _clean_text(row.get("local_video_path"))
            split = _clean_text(row.get("split")) or (expected_split or "")

            if not stem:
                raise ValueError(f"Empty video_stem at {eval_csv}:{line_no}")
            if not local:
                raise ValueError(
                    f"Empty local_video_path for {stem} at {eval_csv}:{line_no}"
                )
            if expected_split and split != expected_split:
                raise ValueError(
                    f"Split mismatch for {stem}: CSV has {split!r}, expected {expected_split!r}"
                )
            if stem in seen_stems:
                raise ValueError(f"Duplicate video_stem in evaluation CSV: {stem}")

            local_path = Path(local)
            normalized_local = str(local_path.absolute())
            if normalized_local in seen_paths:
                raise ValueError(
                    f"Multiple evaluation rows resolve to the same local_video_path: {local_path}"
                )

            uri = _make_s3_uri(row, bucket)
            requests.append(
                VideoRequest(
                    split=split,
                    video_stem=stem,
                    s3_uri=uri,
                    local_path=local_path,
                )
            )
            seen_stems.add(stem)
            seen_paths.add(normalized_local)

    return requests


def _detect_archive_class(output: str) -> str:
    upper = output.upper()
    # Check DEEP_ARCHIVE before GLACIER because diagnostics may mention both.
    if "DEEP_ARCHIVE" in upper:
        return "DEEP_ARCHIVE"
    if re.search(r"\bGLACIER\b", upper):
        return "GLACIER"
    if "INVALIDOBJECTSTATE" in upper:
        # InvalidObjectState from an attempted GET/COPY is an archived-object
        # failure in this workflow. The exact class is not essential to the
        # restore helper; it only needs the S3 URL.
        return "GLACIER"
    return ""


def _is_missing_object(output: str) -> bool:
    lower = output.lower()
    return (
        "nosuchkey" in lower
        or "not found" in lower
        or ("404" in lower and "does not exist" in lower)
        or ("404" in lower and "headobject" in lower)
    )


def _compact_error(output: str, limit: int = 2000) -> str:
    text = " | ".join(line.strip() for line in output.splitlines() if line.strip())
    return text[:limit]


def _archive_log_line(uri: str, archive_class: str) -> str:
    archive_class = archive_class or "GLACIER"
    return (
        f"warning: Skipping file {uri}. Object is of storage class {archive_class}. "
        f"Unable to perform download operations on {archive_class} objects. "
        "You must restore the object to be able to perform the operation."
    )


def _download_one(request: VideoRequest) -> VideoDownloadResult:
    local_path = request.local_path

    if local_path.exists():
        try:
            size = local_path.stat().st_size
        except OSError as exc:
            return VideoDownloadResult(
                split=request.split,
                video_stem=request.video_stem,
                s3_uri=request.s3_uri,
                local_video_path=str(local_path),
                status="error",
                size_bytes=0,
                error=f"Could not stat existing file: {exc}",
            )
        if size > 0:
            return VideoDownloadResult(
                split=request.split,
                video_stem=request.video_stem,
                s3_uri=request.s3_uri,
                local_video_path=str(local_path),
                status="existing",
                size_bytes=size,
            )
        # A zero-byte destination is never considered a valid completed video.
        try:
            local_path.unlink()
        except OSError:
            pass

    local_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = local_path.with_name(local_path.name + ".partial")
    try:
        partial_path.unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [
        "aws",
        "s3",
        "cp",
        request.s3_uri,
        str(partial_path),
        "--only-show-errors",
        "--no-progress",
    ]
    env = os.environ.copy()
    env.setdefault("AWS_RETRY_MODE", "standard")
    env.setdefault("AWS_MAX_ATTEMPTS", "5")

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )
    except Exception as exc:
        return VideoDownloadResult(
            split=request.split,
            video_stem=request.video_stem,
            s3_uri=request.s3_uri,
            local_video_path=str(local_path),
            status="error",
            size_bytes=0,
            error=f"Failed to launch aws CLI: {exc}",
        )

    output = "\n".join(x for x in [proc.stdout or "", proc.stderr or ""] if x)
    archive_class = _detect_archive_class(output)

    # aws s3 cp can report a skipped archived object in its output. Classify
    # based on the diagnostic first instead of assuming returncode semantics.
    if archive_class:
        partial_path.unlink(missing_ok=True)
        return VideoDownloadResult(
            split=request.split,
            video_stem=request.video_stem,
            s3_uri=request.s3_uri,
            local_video_path=str(local_path),
            status="archived",
            size_bytes=0,
            archive_class=archive_class,
            error=_compact_error(output),
        )

    if _is_missing_object(output):
        partial_path.unlink(missing_ok=True)
        return VideoDownloadResult(
            split=request.split,
            video_stem=request.video_stem,
            s3_uri=request.s3_uri,
            local_video_path=str(local_path),
            status="missing",
            size_bytes=0,
            error=_compact_error(output),
        )

    if proc.returncode != 0:
        partial_path.unlink(missing_ok=True)
        return VideoDownloadResult(
            split=request.split,
            video_stem=request.video_stem,
            s3_uri=request.s3_uri,
            local_video_path=str(local_path),
            status="error",
            size_bytes=0,
            error=_compact_error(output) or f"aws s3 cp exited {proc.returncode}",
        )

    if not partial_path.exists() or partial_path.stat().st_size <= 0:
        partial_path.unlink(missing_ok=True)
        return VideoDownloadResult(
            split=request.split,
            video_stem=request.video_stem,
            s3_uri=request.s3_uri,
            local_video_path=str(local_path),
            status="error",
            size_bytes=0,
            error="aws s3 cp returned success but did not create a non-empty file",
        )

    partial_path.replace(local_path)
    size = local_path.stat().st_size
    return VideoDownloadResult(
        split=request.split,
        video_stem=request.video_stem,
        s3_uri=request.s3_uri,
        local_video_path=str(local_path),
        status="downloaded",
        size_bytes=size,
    )


def download_tracking_videos(
    requests: Sequence[VideoRequest],
    *,
    workers: int = 8,
) -> List[VideoDownloadResult]:
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")

    results: List[Optional[VideoDownloadResult]] = [None] * len(requests)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(_download_one, request): idx
            for idx, request in enumerate(requests)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:  # defensive: one worker must not hide the rest
                req = requests[idx]
                results[idx] = VideoDownloadResult(
                    split=req.split,
                    video_stem=req.video_stem,
                    s3_uri=req.s3_uri,
                    local_video_path=str(req.local_path),
                    status="error",
                    size_bytes=0,
                    error=f"Unhandled download worker exception: {exc}",
                )

    return [r for r in results if r is not None]


def write_status_csv(results: Sequence[VideoDownloadResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "split",
        "video_stem",
        "s3_uri",
        "local_video_path",
        "status",
        "size_bytes",
        "archive_class",
        "error",
        "eligible_for_tracking",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row["eligible_for_tracking"] = str(
                result.status in {"existing", "downloaded"}
            ).lower()
            writer.writerow(row)


def write_glacier_log(results: Sequence[VideoDownloadResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    archived: Dict[str, str] = {}
    for result in results:
        if result.status == "archived":
            archived[result.s3_uri] = result.archive_class or "GLACIER"

    lines = [
        _archive_log_line(uri, archived[uri])
        for uri in sorted(archived)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def summarize(results: Sequence[VideoDownloadResult]) -> DownloadStats:
    counts = Counter(r.status for r in results)
    return DownloadStats(
        videos_total=len(results),
        existing=counts["existing"],
        downloaded=counts["downloaded"],
        archived=counts["archived"],
        missing=counts["missing"],
        errors=counts["error"],
        bytes_present=sum(
            r.size_bytes
            for r in results
            if r.status in {"existing", "downloaded"}
        ),
    )


def write_summary_json(stats: DownloadStats, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(stats), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Materialize full source videos for a tracking-evaluation split. "
            "Archived S3 objects are written to a restore-helper-compatible log."
        )
    )
    p.add_argument("--eval-csv", required=True, type=Path)
    p.add_argument("--split", required=True, choices=["val", "test"])
    p.add_argument("--bucket", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--status-csv", required=True, type=Path)
    p.add_argument("--summary-json", required=True, type=Path)
    p.add_argument("--glacier-log", required=True, type=Path)
    p.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Treat permanent S3 404/NoSuchKey objects as a stage failure.",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")

    requests = read_video_requests(
        args.eval_csv,
        bucket=args.bucket,
        expected_split=args.split,
    )
    results = download_tracking_videos(requests, workers=args.workers)
    write_status_csv(results, args.status_csv)
    write_glacier_log(results, args.glacier_log)
    stats = summarize(results)
    write_summary_json(stats, args.summary_json)

    print(
        "Tracking videos: "
        f"total={stats.videos_total} existing={stats.existing} "
        f"downloaded={stats.downloaded} archived={stats.archived} "
        f"missing={stats.missing} errors={stats.errors}"
    )

    for result in results:
        if result.status in {"archived", "missing", "error"}:
            detail = f" ({result.error})" if result.error else ""
            print(
                f"[tracking-video] {result.status.upper():8s} "
                f"{result.video_stem}: {result.s3_uri}{detail}",
                file=sys.stderr,
            )

    if stats.archived:
        print(
            f"\n{stats.archived} archived video(s) need restore. "
            f"The restore-helper-compatible log is:\n  {args.glacier_log}\n\n"
            "Example:\n"
            f"  scripts/restore_glacier_from_log.sh request {args.glacier_log} 3 Bulk 32\n"
            "Then check with:\n"
            f"  scripts/restore_glacier_from_log.sh status {args.glacier_log} 32\n",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if stats.errors:
        raise SystemExit(
            f"{stats.errors} video download(s) failed for transient/unknown reasons; "
            f"see {args.status_csv}"
        )

    if args.fail_on_missing and stats.missing:
        raise SystemExit(
            f"{stats.missing} source video(s) are missing from S3; see {args.status_csv}"
        )

    if stats.missing:
        print(
            f"WARNING: {stats.missing} source video(s) are permanently missing and "
            "are marked eligible_for_tracking=false in the status CSV.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
