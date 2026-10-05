from __future__ import annotations

import argparse
import configparser
import csv
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SequenceInfo:
    split: str
    video_stem: str
    status: str
    width: int
    height: int
    fps: float
    nb_frames: int
    n_tracks: int
    n_gt_rows: int
    rotated_rows: int


@dataclass(frozen=True)
class MotGtRow:
    video_stem: str
    mot_frame: int
    track_id: int
    left: float
    top: float
    width: float
    height: float
    rotation_deg: float


@dataclass
class MaterializeStats:
    split: str = ""
    benchmark: str = ""
    sequences_written: int = 0
    zero_gt_sequences: int = 0
    gt_rows_written: int = 0
    tracks_written: int = 0
    rotated_rows: int = 0


def _as_int(value: object, *, field: str, context: str) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"Missing {field} for {context}")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}={value!r} for {context}") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"Invalid integer {field}={value!r} for {context}")
    return int(number)


def _as_float(value: object, *, field: str, context: str) -> float:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"Missing {field} for {context}")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}={value!r} for {context}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {field}={value!r} for {context}")
    return number


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def read_sequence_info(path: Path, *, expected_split: Optional[str] = None) -> Dict[str, SequenceInfo]:
    path = Path(path)
    out: Dict[str, SequenceInfo] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Sequences CSV has no header: {path}")
        required = {
            "split", "video_stem", "status", "width", "height", "fps",
            "nb_frames", "n_tracks", "n_gt_rows", "rotated_rows",
        }
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"Sequences CSV missing columns {sorted(missing)}: {path}")

        for row_no, row in enumerate(reader, start=2):
            stem = (row.get("video_stem") or "").strip()
            context = f"{path}:{row_no}"
            if not stem:
                raise ValueError(f"Missing video_stem for {context}")
            if stem in out:
                raise ValueError(f"Duplicate sequence {stem!r} in {path}")

            split = (row.get("split") or "").strip()
            if not split:
                raise ValueError(f"Missing split for {context}")
            if expected_split is not None and split != expected_split:
                raise ValueError(
                    f"Sequence {stem} belongs to split {split!r}, expected {expected_split!r}"
                )

            width = _as_int(row.get("width"), field="width", context=context)
            height = _as_int(row.get("height"), field="height", context=context)
            fps = _as_float(row.get("fps"), field="fps", context=context)
            nb_frames = _as_int(row.get("nb_frames"), field="nb_frames", context=context)
            n_tracks = _as_int(row.get("n_tracks"), field="n_tracks", context=context)
            n_gt_rows = _as_int(row.get("n_gt_rows"), field="n_gt_rows", context=context)
            rotated_rows = _as_int(row.get("rotated_rows"), field="rotated_rows", context=context)

            if width <= 0 or height <= 0:
                raise ValueError(f"Non-positive dimensions for {stem}: {width}x{height}")
            if fps <= 0:
                raise ValueError(f"Non-positive fps for {stem}: {fps}")
            if nb_frames <= 0:
                raise ValueError(f"Non-positive nb_frames for {stem}: {nb_frames}")
            if n_tracks < 0 or n_gt_rows < 0 or rotated_rows < 0:
                raise ValueError(f"Negative count in sequence metadata for {stem}")

            status = (row.get("status") or "").strip()
            allowed_statuses = {"ok", "no_tracks", "condition_negative"}
            if status not in allowed_statuses:
                raise ValueError(
                    f"Sequence {stem} has non-evaluable GT status {status!r}; "
                    f"expected one of {sorted(allowed_statuses)}"
                )
            if status == "ok" and n_tracks <= 0:
                raise ValueError(f"Sequence {stem} has status='ok' but n_tracks={n_tracks}")
            if status in {"no_tracks", "condition_negative"} and (n_tracks != 0 or n_gt_rows != 0):
                raise ValueError(
                    f"Zero-GT sequence {stem} has status={status!r} but "
                    f"n_tracks={n_tracks} n_gt_rows={n_gt_rows}"
                )

            out[stem] = SequenceInfo(
                split=split,
                video_stem=stem,
                status=status,
                width=width,
                height=height,
                fps=fps,
                nb_frames=nb_frames,
                n_tracks=n_tracks,
                n_gt_rows=n_gt_rows,
                rotated_rows=rotated_rows,
            )

    if not out:
        raise RuntimeError(f"No sequences found in: {path}")
    return out


def read_gt_rows(path: Path, *, expected_split: Optional[str] = None) -> Dict[str, List[MotGtRow]]:
    path = Path(path)
    grouped: Dict[str, List[MotGtRow]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"GT CSV has no header: {path}")
        required = {
            "split", "video_stem", "mot_frame", "track_id",
            "x_px", "y_px", "width_px", "height_px", "rotation_deg",
        }
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"GT CSV missing columns {sorted(missing)}: {path}")

        for row_no, row in enumerate(reader, start=2):
            stem = (row.get("video_stem") or "").strip()
            context = f"{path}:{row_no}"
            if not stem:
                raise ValueError(f"Missing video_stem for {context}")
            split = (row.get("split") or "").strip()
            if expected_split is not None and split != expected_split:
                raise ValueError(
                    f"GT row for {stem} belongs to split {split!r}, expected {expected_split!r}"
                )

            frame = _as_int(row.get("mot_frame"), field="mot_frame", context=context)
            track_id = _as_int(row.get("track_id"), field="track_id", context=context)
            x = _as_float(row.get("x_px"), field="x_px", context=context)
            y = _as_float(row.get("y_px"), field="y_px", context=context)
            width = _as_float(row.get("width_px"), field="width_px", context=context)
            height = _as_float(row.get("height_px"), field="height_px", context=context)
            rotation = _as_float(
                row.get("rotation_deg") if row.get("rotation_deg") not in (None, "") else 0,
                field="rotation_deg",
                context=context,
            )

            if frame < 1:
                raise ValueError(f"MOT frame must be >= 1 for {stem}: {frame}")
            if track_id < 1:
                raise ValueError(f"MOT track_id must be >= 1 for {stem}: {track_id}")
            if width <= 0 or height <= 0:
                raise ValueError(
                    f"MOT box must have positive width/height for {stem}: {width}x{height}"
                )

            grouped.setdefault(stem, []).append(
                MotGtRow(
                    video_stem=stem,
                    mot_frame=frame,
                    track_id=track_id,
                    left=x + 1.0,
                    top=y + 1.0,
                    width=width,
                    height=height,
                    rotation_deg=rotation,
                )
            )
    return grouped


def format_motchallenge_gt_row(row: MotGtRow) -> str:
    """
    MOT16/17-style ground-truth row used by TrackEval's MotChallenge2DBox:

      frame,id,bb_left,bb_top,bb_width,bb_height,mark,class,visibility

    We intentionally map all SalmonVision objects to MOT class 1 because the
    stock MotChallenge2DBox dataset supports one evaluation class. Species are
    retained in the canonical CSV and can be evaluated separately later.
    """
    values = [
        str(row.mot_frame),
        str(row.track_id),
        f"{row.left:.6f}",
        f"{row.top:.6f}",
        f"{row.width:.6f}",
        f"{row.height:.6f}",
        "1",
        "1",
        "1.000000",
    ]
    return ",".join(values)


def validate_motchallenge_gt_lines(lines: Iterable[str], *, seq_length: int, sequence: str) -> None:
    seen: set[Tuple[int, int]] = set()
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 9:
            raise ValueError(
                f"{sequence} gt.txt line {line_no} must contain 9 MOT GT columns, got {len(parts)}"
            )
        frame = _as_int(parts[0], field="frame", context=f"{sequence}:{line_no}")
        track_id = _as_int(parts[1], field="id", context=f"{sequence}:{line_no}")
        left = _as_float(parts[2], field="bb_left", context=f"{sequence}:{line_no}")
        top = _as_float(parts[3], field="bb_top", context=f"{sequence}:{line_no}")
        width = _as_float(parts[4], field="bb_width", context=f"{sequence}:{line_no}")
        height = _as_float(parts[5], field="bb_height", context=f"{sequence}:{line_no}")
        mark = _as_int(parts[6], field="mark", context=f"{sequence}:{line_no}")
        class_id = _as_int(parts[7], field="class", context=f"{sequence}:{line_no}")
        visibility = _as_float(parts[8], field="visibility", context=f"{sequence}:{line_no}")

        if frame < 1 or frame > seq_length:
            raise ValueError(f"Frame {frame} outside 1..{seq_length} in {sequence}")
        if track_id < 1:
            raise ValueError(f"Track ID must be >= 1 in {sequence}")
        if left < 1 or top < 1:
            raise ValueError(f"MOT bb_left/bb_top must be 1-based (>=1) in {sequence}")
        if width <= 0 or height <= 0:
            raise ValueError(f"MOT width/height must be positive in {sequence}")
        if mark != 1:
            raise ValueError(f"Ground-truth mark must be 1 in {sequence}")
        if class_id != 1:
            raise ValueError(f"Ground-truth MOT compatibility class must be 1 in {sequence}")
        if not 0.0 <= visibility <= 1.0:
            raise ValueError(f"Visibility must be in [0,1] in {sequence}")
        key = (frame, track_id)
        if key in seen:
            raise ValueError(f"Duplicate (frame,id)={key} in {sequence}")
        seen.add(key)


def _write_seqinfo(path: Path, seq: SequenceInfo) -> None:
    text = "\n".join(
        [
            "[Sequence]",
            f"name={seq.video_stem}",
            "imDir=img1",
            f"frameRate={_format_number(seq.fps)}",
            f"seqLength={seq.nb_frames}",
            f"imWidth={seq.width}",
            f"imHeight={seq.height}",
            "imExt=.jpg",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def validate_seqinfo(path: Path, seq: SequenceInfo) -> None:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if "Sequence" not in parser:
        raise ValueError(f"Missing [Sequence] section in {path}")
    section = parser["Sequence"]
    expected = {
        "name": seq.video_stem,
        "imdir": "img1",
        "seqlength": str(seq.nb_frames),
        "imwidth": str(seq.width),
        "imheight": str(seq.height),
        "imext": ".jpg",
    }
    for key, value in expected.items():
        if section.get(key) != value:
            raise ValueError(f"Invalid seqinfo {key} for {seq.video_stem}: {section.get(key)!r}")
    if float(section.get("framerate", "0")) <= 0:
        raise ValueError(f"Invalid seqinfo frameRate for {seq.video_stem}")


def materialize_mot_ground_truth(
    *,
    gt_csv: Path,
    sequences_csv: Path,
    out_root: Path,
    benchmark: str,
    split: str,
    summary_json: Optional[Path] = None,
    allow_rotated: bool = False,
) -> MaterializeStats:
    benchmark = benchmark.strip()
    split = split.strip()
    if not benchmark:
        raise ValueError("benchmark must not be empty")
    if not split:
        raise ValueError("split must not be empty")
    if any(ch in benchmark for ch in "/\\"):
        raise ValueError(f"benchmark must be a simple name, got {benchmark!r}")
    if any(ch in split for ch in "/\\"):
        raise ValueError(f"split must be a simple name, got {split!r}")

    sequences = read_sequence_info(sequences_csv, expected_split=split)
    gt_by_sequence = read_gt_rows(gt_csv, expected_split=split)

    extra_gt = sorted(set(gt_by_sequence).difference(sequences))
    if extra_gt:
        raise ValueError(
            "GT CSV contains sequence(s) absent from sequences CSV: " + ", ".join(extra_gt[:20])
        )

    stats = MaterializeStats(split=split, benchmark=benchmark)

    for stem, seq in sequences.items():
        rows = gt_by_sequence.get(stem, [])
        unique_tracks = {row.track_id for row in rows}
        rotated = sum(abs(row.rotation_deg) > 1e-9 for row in rows)

        if len(rows) != seq.n_gt_rows:
            raise ValueError(
                f"n_gt_rows mismatch for {stem}: sequences CSV says {seq.n_gt_rows}, GT CSV has {len(rows)}"
            )
        if len(unique_tracks) != seq.n_tracks:
            raise ValueError(
                f"n_tracks mismatch for {stem}: sequences CSV says {seq.n_tracks}, GT CSV has {len(unique_tracks)}"
            )
        if rotated != seq.rotated_rows:
            raise ValueError(
                f"rotated_rows mismatch for {stem}: sequences CSV says {seq.rotated_rows}, GT CSV has {rotated}"
            )
        if rotated and not allow_rotated:
            raise ValueError(
                f"Sequence {stem} contains {rotated} rotated GT row(s); MOTChallenge boxes are axis-aligned. "
                "Pass --allow-rotated only if the canonical x/y/width/height representation is intentional."
            )

        seen: set[Tuple[int, int]] = set()
        for row in rows:
            if row.mot_frame > seq.nb_frames:
                raise ValueError(
                    f"GT frame {row.mot_frame} exceeds seqLength={seq.nb_frames} for {stem}"
                )
            if row.left < 1 or row.top < 1:
                raise ValueError(
                    f"MOTChallenge 1-based bbox origin became invalid for {stem}: left={row.left}, top={row.top}"
                )
            key = (row.mot_frame, row.track_id)
            if key in seen:
                raise ValueError(f"Duplicate (mot_frame,track_id)={key} for {stem}")
            seen.add(key)

        stats.sequences_written += 1
        stats.gt_rows_written += len(rows)
        stats.tracks_written += len(unique_tracks)
        stats.rotated_rows += rotated
        if not rows:
            stats.zero_gt_sequences += 1

    out_root = Path(out_root)
    split_root = out_root / f"{benchmark}-{split}"
    seqmap_dir = out_root / "seqmaps"
    seqmap_path = seqmap_dir / f"{benchmark}-{split}.txt"

    # The split folder is a derived materialization. Rebuild it cleanly so
    # removed sequences cannot survive as stale TrackEval inputs.
    if split_root.exists():
        shutil.rmtree(split_root)
    split_root.mkdir(parents=True, exist_ok=True)
    seqmap_dir.mkdir(parents=True, exist_ok=True)

    ordered_sequences = sorted(sequences.values(), key=lambda s: s.video_stem)
    for seq in ordered_sequences:
        seq_dir = split_root / seq.video_stem
        gt_dir = seq_dir / "gt"
        gt_dir.mkdir(parents=True, exist_ok=True)

        rows = sorted(
            gt_by_sequence.get(seq.video_stem, []),
            key=lambda row: (row.mot_frame, row.track_id),
        )
        gt_lines = [format_motchallenge_gt_row(row) for row in rows]
        gt_path = gt_dir / "gt.txt"
        gt_path.write_text("\n".join(gt_lines) + ("\n" if gt_lines else ""), encoding="utf-8")
        validate_motchallenge_gt_lines(
            gt_path.read_text(encoding="utf-8").splitlines(),
            seq_length=seq.nb_frames,
            sequence=seq.video_stem,
        )

        seqinfo_path = seq_dir / "seqinfo.ini"
        _write_seqinfo(seqinfo_path, seq)
        validate_seqinfo(seqinfo_path, seq)

    seqmap_text = "name\n" + "\n".join(seq.video_stem for seq in ordered_sequences) + "\n"
    seqmap_path.write_text(seqmap_text, encoding="utf-8")

    if summary_json is not None:
        summary_path = Path(summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(asdict(stats), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return stats


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Materialize canonical tracking GT CSVs into TrackEval/MOTChallenge ground-truth layout."
    )
    p.add_argument("--gt-csv", required=True, type=Path)
    p.add_argument("--sequences-csv", required=True, type=Path)
    p.add_argument("--out-root", required=True, type=Path)
    p.add_argument("--benchmark", required=True)
    p.add_argument("--split", required=True)
    p.add_argument("--summary-json", type=Path, default=None)
    p.add_argument(
        "--allow-rotated",
        action="store_true",
        help="Allow rows whose canonical GT reports non-zero rotation; MOT output remains axis-aligned.",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    stats = materialize_mot_ground_truth(
        gt_csv=args.gt_csv,
        sequences_csv=args.sequences_csv,
        out_root=args.out_root,
        benchmark=args.benchmark,
        split=args.split,
        summary_json=args.summary_json,
        allow_rotated=args.allow_rotated,
    )
    print(
        "MOT GT materialized: "
        f"benchmark={stats.benchmark} split={stats.split} "
        f"sequences={stats.sequences_written} zero_gt_sequences={stats.zero_gt_sequences} "
        f"tracks={stats.tracks_written} gt_rows={stats.gt_rows_written} "
        f"rotated_rows={stats.rotated_rows}"
    )


if __name__ == "__main__":
    main()
