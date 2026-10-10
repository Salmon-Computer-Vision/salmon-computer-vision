"""Continuous per-video YOLO tracking with local resumable shards and one DVC Parquet output.

Coordinates and frame indices in the canonical Parquet are 0-based.  MOT rows
are created later using mot_frame (1-based) and x_px/y_px + 1.

Only COMPLETED sequences may be used in tracking/count evaluation.  Unavailable,
failed, or frame-count-inconsistent videos are recorded in the status table.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence


PREDICTION_COLUMNS = (
    "split", "site", "video_stem", "frame_idx", "mot_frame", "track_id",
    "class_id", "confidence", "x_px", "y_px", "width_px", "height_px",
)
STATUS_COLUMNS = (
    "split", "site", "video_stem", "local_video_path", "download_status",
    "status", "eligible_for_evaluation", "frames_decoded", "gt_nb_frames",
    "container_nb_frames", "predictions_written", "untracked_detections",
    "unique_track_ids", "width", "height", "fps", "elapsed_seconds",
    "reused_cache", "error",
)
FORMAT_VERSION = "salmonvision-tracking-inference-v1"


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "PyArrow is required for tracking inference. Add 'pyarrow>=16' to "
            "pyproject.toml and run `uv sync --extra cu124` (or your CUDA extra)."
        ) from exc
    return pa, pq


def prediction_schema():
    pa, _ = _arrow()
    return pa.schema([
        ("split", pa.string()), ("site", pa.string()), ("video_stem", pa.string()),
        ("frame_idx", pa.int32()), ("mot_frame", pa.int32()),
        ("track_id", pa.int64()), ("class_id", pa.int32()),
        ("confidence", pa.float32()),
        ("x_px", pa.float32()), ("y_px", pa.float32()),
        ("width_px", pa.float32()), ("height_px", pa.float32()),
    ])


def _parquet_rows(path: Path) -> int:
    _, pq = _arrow()
    return pq.ParquetFile(path).metadata.num_rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _value(row: dict, name: str) -> str:
    return str(row.get(name) or "").strip()


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        return list(reader)


def _int_field(value: str, name: str, stem: str, *, default: int = 0) -> int:
    if not value:
        return default
    try:
        v = float(value)
    except ValueError as exc:
        raise ValueError(f"{stem}: invalid {name}={value!r}") from exc
    if not math.isfinite(v) or v < 0 or not v.is_integer():
        raise ValueError(f"{stem}: invalid {name}={value!r}")
    return int(v)


@dataclass(frozen=True)
class Task:
    split: str
    site: str
    video_stem: str
    path: Path
    download_status: str
    gt_nb_frames: int
    gt_width: int
    gt_height: int


def read_tasks(eval_csv: Path, status_csv: Path, sequences_csv: Path, split: str) -> list[Task]:
    evaluation = _read_csv(eval_csv, {"split", "video_stem", "local_video_path"})
    downloads = _read_csv(status_csv, {"split", "video_stem", "status", "local_video_path"})
    sequences = _read_csv(sequences_csv, {"split", "video_stem", "nb_frames", "width", "height"})

    def keyed(rows: list[dict[str, str]], origin: str) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for row in rows:
            stem = _value(row, "video_stem")
            if (not stem or Path(stem).name != stem or stem in (".", "..")
                    or "/" in stem or "\\" in stem):
                raise ValueError(f"Invalid video_stem in {origin}: {stem!r}")
            if _value(row, "split") != split:
                raise ValueError(f"{origin}: split mismatch for {stem}: {row.get('split')!r}")
            if stem in out:
                raise ValueError(f"{origin}: duplicate video_stem={stem}")
            out[stem] = row
        return out

    eval_map = keyed(evaluation, str(eval_csv))
    status_map = keyed(downloads, str(status_csv))
    seq_map = keyed(sequences, str(sequences_csv))
    for name, other in [("download status", status_map), ("GT sequences", seq_map)]:
        if set(eval_map) != set(other):
            raise ValueError(
                f"{name} and eval CSV contain different video sets. "
                f"Missing: {sorted(set(eval_map)-set(other))[:5]}; "
                f"extra: {sorted(set(other)-set(eval_map))[:5]}"
            )
    tasks = []
    for stem in sorted(eval_map):
        e, d, s = eval_map[stem], status_map[stem], seq_map[stem]
        if Path(_value(e, "local_video_path")).resolve() != Path(_value(d, "local_video_path")).resolve():
            raise ValueError(f"Different local video paths for {stem}")
        site = _value(e, "site") or _value(s, "site")
        if _value(e, "site") and _value(s, "site") and _value(e, "site") != _value(s, "site"):
            raise ValueError(f"Different sites for {stem}")
        tasks.append(Task(
            split=split, site=site, video_stem=stem,
            path=Path(_value(e, "local_video_path")),
            download_status=_value(d, "status"),
            gt_nb_frames=_int_field(_value(s, "nb_frames"), "nb_frames", stem),
            gt_width=_int_field(_value(s, "width"), "width", stem),
            gt_height=_int_field(_value(s, "height"), "height", stem),
        ))
    return tasks


@dataclass(frozen=True)
class Settings:
    tracker: str
    conf: float
    iou: float
    imgsz: int
    device: str

    def validate(self) -> None:
        if not (0 < self.conf <= 1 and 0 < self.iou <= 1):
            raise ValueError("conf and iou must be in (0,1]")
        if self.imgsz <= 0:
            raise ValueError("imgsz must be > 0")
        if not self.tracker:
            raise ValueError("tracker must be provided")


def tracker_fingerprint(name: str) -> str:
    # Hash a user-supplied YAML; built-in botsort.yaml/bytetrack.yaml is included
    # with the pinned ultralytics version in the run fingerprint.
    path = Path(name)
    return _sha256_file(path) if path.is_file() else name


def run_fingerprint(model: Path, settings: Settings, *, ultralytics_version: str,
                    cv2_version: str) -> str:
    settings.validate()
    if not model.is_file():
        raise FileNotFoundError(f"Model not found: {model}")
    return _digest({
        "format": FORMAT_VERSION,
        "model_sha256": _sha256_file(model),
        "settings": asdict(settings),
        "tracker_config": tracker_fingerprint(settings.tracker),
        "ultralytics": ultralytics_version,
        "opencv": cv2_version,
        "source_sha256": _sha256_file(Path(__file__)),
    })


def video_fingerprint(task: Task, settings_fingerprint: str) -> str:
    stat = task.path.stat()
    return _digest({
        "settings_fingerprint": settings_fingerprint,
        "video_path": str(task.path.resolve()),
        "video_size": stat.st_size,
        "video_mtime_ns": stat.st_mtime_ns,
        "split": task.split,
        "site": task.site,
        "video_stem": task.video_stem,
        "gt_nb_frames": task.gt_nb_frames,
        "gt_width": task.gt_width,
        "gt_height": task.gt_height,
    })


def reset_trackers(model: Any) -> None:
    """Reset ALL Ultralytics trackers; never leak identities across MP4s."""
    predictor = getattr(model, "predictor", None)
    if predictor is None:
        return  # fresh model; first model.track() creates the tracker
    trackers = getattr(predictor, "trackers", None)
    if not trackers:
        raise RuntimeError("Ultralytics predictor exists without trackers; refusing unsafe reuse")
    for tracker in trackers:
        reset = getattr(tracker, "reset", None)
        if not callable(reset):
            raise RuntimeError("Ultralytics tracker has no reset() method")
        reset()
    if hasattr(predictor, "vid_path"):
        predictor.vid_path = [None] * len(getattr(predictor, "vid_path", []) or [None])


def _arrays_from_result(result: Any) -> tuple[list, list, list, list, int]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return [], [], [], [], 0
    ids_tensor = getattr(boxes, "id", None)
    if ids_tensor is None:
        return [], [], [], [], len(boxes)

    def aslist(tensor: Any) -> list:
        if hasattr(tensor, "cpu"):
            tensor = tensor.cpu()
        if hasattr(tensor, "numpy"):
            tensor = tensor.numpy()
        return tensor.tolist() if hasattr(tensor, "tolist") else list(tensor)

    ids = aslist(ids_tensor)
    coords = aslist(boxes.xyxy)
    classes = aslist(boxes.cls)
    scores = aslist(boxes.conf)
    if not (len(ids) == len(coords) == len(classes) == len(scores) == len(boxes)):
        raise ValueError("Ultralytics returned unequal box / id / class / confidence lengths")
    return ids, coords, classes, scores, 0


def rows_for_result(result: Any, *, task: Task, frame_idx: int, width: int,
                    height: int) -> tuple[list[dict], int]:
    ids, coords, classes, scores, untracked = _arrays_from_result(result)
    rows = []
    seen: set[int] = set()
    for tid, bb, cls, score in zip(ids, coords, classes, scores):
        if len(bb) != 4 or not all(math.isfinite(float(x)) for x in [tid, cls, score, *bb]):
            raise ValueError(f"{task.video_stem} frame {frame_idx}: non-finite prediction")
        if not float(tid).is_integer() or int(tid) < 1:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: invalid track ID {tid!r}")
        if not float(cls).is_integer() or int(cls) < 0:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: invalid class ID {cls!r}")
        if not 0 <= float(score) <= 1:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: invalid confidence {score!r}")
        track_id = int(tid)
        if track_id in seen:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: duplicate track ID {track_id}")
        seen.add(track_id)
        x1, y1, x2, y2 = map(float, bb)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: invalid XYXY box {bb}")
        x1, y1 = max(0., min(x1, width)), max(0., min(y1, height))
        x2, y2 = max(0., min(x2, width)), max(0., min(y2, height))
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"{task.video_stem} frame {frame_idx}: box outside image {bb}")
        rows.append({
            "split": task.split, "site": task.site, "video_stem": task.video_stem,
            "frame_idx": frame_idx, "mot_frame": frame_idx + 1,
            "track_id": track_id, "class_id": int(cls),
            "confidence": float(score), "x_px": x1, "y_px": y1,
            "width_px": x2-x1, "height_px": y2-y1,
        })
    return rows, untracked


def _to_table(rows: list[dict]):
    pa, _ = _arrow()
    return pa.Table.from_pylist(rows, schema=prediction_schema())


def _atomic_parquet(rows: list[dict], path: Path) -> None:
    _, pq = _arrow()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        pq.write_table(_to_table(rows), tmp, compression="zstd")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_json_atomic(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _frame_tolerance(reference: int) -> int:
    return max(2, int(math.ceil(reference * 0.01)))


def infer_video(task: Task, model: Any, settings: Settings, capture_factory: Callable,
                cv2_module: Any) -> tuple[list[dict], dict]:
    cap = capture_factory(str(task.path))
    started = time.monotonic()
    rows: list[dict] = []
    frame_idx = 0
    untracked = 0
    ids: set[int] = set()
    width = height = 0
    fps = 0.0
    reported_frames = 0
    try:
        if not cap.isOpened():
            raise OSError(f"Unable to open video: {task.path}")
        n = float(cap.get(cv2_module.CAP_PROP_FRAME_COUNT))
        if math.isfinite(n) and n > 0:
            reported_frames = int(round(n))
        reported_fps = float(cap.get(cv2_module.CAP_PROP_FPS))
        if math.isfinite(reported_fps) and reported_fps > 0:
            fps = reported_fps
        reset_trackers(model)
        while True:
            success, frame = cap.read()
            if not success:
                break
            if frame is None or len(frame.shape) < 2:
                raise ValueError(f"{task.video_stem}: decoder returned an invalid frame")
            h, w = frame.shape[:2]
            if width == 0:
                width, height = w, h
            if (w, h) != (width, height):
                raise ValueError(f"{task.video_stem}: frame resolution changed at {frame_idx}")
            result = model.track(
                source=frame, persist=True, tracker=settings.tracker,
                conf=settings.conf, iou=settings.iou, imgsz=settings.imgsz,
                device=settings.device, verbose=False, save=False,
            )
            if len(result) != 1:
                raise ValueError(f"{task.video_stem}: expected one result per decoded frame")
            new, pending = rows_for_result(
                result[0], task=task, frame_idx=frame_idx, width=w, height=h,
            )
            rows.extend(new)
            untracked += pending
            ids.update(r["track_id"] for r in new)
            frame_idx += 1
    finally:
        cap.release()

    if not frame_idx:
        raise ValueError(f"No decodable frames in {task.path}")
    error = ""
    # Frame-count/metadata inconsistencies are not silently evaluated.
    problems = []
    for label, reference in [("container", reported_frames), ("GT metadata", task.gt_nb_frames)]:
        if reference > 0 and abs(frame_idx - reference) > _frame_tolerance(reference):
            problems.append(f"{label} expected {reference} frames but decoded {frame_idx}")
    if task.gt_width and task.gt_height and (width, height) != (task.gt_width, task.gt_height):
        problems.append(
            f"GT resolution {task.gt_width}x{task.gt_height} vs video {width}x{height}"
        )
    if problems:
        raise ValueError("; ".join(problems))

    return rows, {
        "frames_decoded": frame_idx, "container_nb_frames": reported_frames,
        "predictions_written": len(rows), "untracked_detections": untracked,
        "unique_track_ids": len(ids), "width": width, "height": height,
        "fps": fps, "elapsed_seconds": round(time.monotonic()-started, 3),
    }


def _empty_status(task: Task, status: str, error: str = "") -> dict:
    return {
        "split": task.split, "site": task.site, "video_stem": task.video_stem,
        "local_video_path": str(task.path), "download_status": task.download_status,
        "status": status, "eligible_for_evaluation": status == "ok",
        "frames_decoded": 0, "gt_nb_frames": task.gt_nb_frames,
        "container_nb_frames": 0, "predictions_written": 0,
        "untracked_detections": 0, "unique_track_ids": 0,
        "width": 0, "height": 0, "fps": 0.0, "elapsed_seconds": 0.0,
        "reused_cache": False, "error": error,
    }


def _cache_paths(cache_dir: Path, task: Task) -> tuple[Path, Path]:
    return cache_dir / f"{task.video_stem}.parquet", cache_dir / f"{task.video_stem}.json"


def _load_cache(cache_dir: Path, task: Task, key: str) -> dict | None:
    parquet_path, metadata_path = _cache_paths(cache_dir, task)
    if not parquet_path.is_file() or not metadata_path.is_file():
        return None
    try:
        obj = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (obj.get("cache_key") != key or obj.get("status") != "ok"
                or obj.get("video_stem") != task.video_stem
                or obj.get("predictions_written") != _parquet_rows(parquet_path)):
            return None
        _, pq = _arrow()
        if not pq.ParquetFile(parquet_path).schema_arrow.equals(prediction_schema()):
            return None
        return obj
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _merge_parquets(tasks: list[Task], statuses: list[dict], cache_dir: Path,
                    output_path: Path) -> None:
    pa, pq = _arrow()
    schema = prediction_schema()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".partial")
    writer = None
    try:
        writer = pq.ParquetWriter(tmp, schema=schema, compression="zstd")
        for task, status in zip(tasks, statuses):
            if status["status"] != "ok":
                continue
            shard, _ = _cache_paths(cache_dir, task)
            # Stream row-groups rather than loading all predictions into RAM.
            source = pq.ParquetFile(shard)
            if not source.schema_arrow.equals(schema):
                raise ValueError(f"Schema mismatch in cached shard {shard}")
            for batch in source.iter_batches(batch_size=65536):
                writer.write_batch(batch)
        writer.close()
        writer = None
        os.replace(tmp, output_path)
    finally:
        if writer is not None:
            writer.close()
        tmp.unlink(missing_ok=True)


def _write_status_csv(path: Path, statuses: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=STATUS_COLUMNS)
            writer.writeheader()
            for row in statuses:
                writer.writerow(row)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def infer_split(*, tasks: list[Task], settings: Settings, model_path: Path,
                cache_dir: Path, predictions_path: Path, status_path: Path,
                summary_path: Path, backend_factory: Optional[Callable] = None,
                cv2_module: Any = None, ultralytics_version: str = "unknown") -> dict:
    if cv2_module is None:
        import cv2 as cv2_module
    if backend_factory is None:
        from ultralytics import YOLO, __version__
        backend_factory = YOLO
        ultralytics_version = __version__

    signature = run_fingerprint(
        model_path, settings, ultralytics_version=ultralytics_version,
        cv2_version=str(getattr(cv2_module, "__version__", "unknown")),
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    backend = None  # avoid GPU initialization if every video is cached/unavailable
    statuses: list[dict] = []
    for index, task in enumerate(tasks, 1):
        result = _empty_status(task, "unavailable")
        if task.download_status not in {"existing", "downloaded"}:
            result["error"] = f"download status: {task.download_status}"
            if task.download_status not in {"archived", "missing"}:
                result["status"] = "error"
        elif not task.path.is_file() or task.path.stat().st_size <= 0:
            result["status"] = "missing_local_video"
            result["error"] = f"File missing or zero bytes: {task.path}"
        else:
            key = video_fingerprint(task, signature)
            entry = _load_cache(cache_dir, task, key)
            if entry is not None:
                result.update(entry["stats"])
                result["status"] = "ok"
                result["eligible_for_evaluation"] = True
                result["reused_cache"] = True
            else:
                try:
                    if backend is None:
                        try:
                            backend = backend_factory(str(model_path))
                        except Exception as exc:
                            raise RuntimeError(
                                f"Cannot initialize YOLO checkpoint {model_path}: {exc}"
                            ) from exc
                    rows, stats = infer_video(
                        task, backend, settings, capture_factory=cv2_module.VideoCapture,
                        cv2_module=cv2_module,
                    )
                    shard, meta = _cache_paths(cache_dir, task)
                    _atomic_parquet(rows, shard)
                    _write_json_atomic({
                        "cache_key": key, "status": "ok", "video_stem": task.video_stem,
                        "predictions_written": len(rows), "stats": stats,
                    }, meta)
                    result.update(stats)
                    result["status"] = "ok"
                    result["eligible_for_evaluation"] = True
                except Exception as exc:
                    if isinstance(exc, RuntimeError) and str(exc).startswith("Cannot initialize YOLO checkpoint"):
                        raise
                    result["status"] = "error"
                    result["error"] = f"{type(exc).__name__}: {exc}"[:3000]
                    # A stale shard from an earlier version must not be reused.
                    shard, meta = _cache_paths(cache_dir, task)
                    meta.unlink(missing_ok=True)
        statuses.append(result)
        print(
            f"[{index}/{len(tasks)}] {task.video_stem}: {result['status']} "
            f"frames={result['frames_decoded']} rows={result['predictions_written']} "
            f"cached={result['reused_cache']}", flush=True,
        )

    # Write a valid empty Parquet when no videos are available or no fish are tracked.
    _merge_parquets(tasks, statuses, cache_dir, predictions_path)
    _write_status_csv(status_path, statuses)
    counts = Counter(r["status"] for r in statuses)
    summary = {
        "format_version": FORMAT_VERSION,
        "settings_fingerprint": signature,
        "split": tasks[0].split if tasks else "",
        "videos_selected": len(tasks),
        "videos_ok": counts["ok"],
        "videos_unavailable": counts["unavailable"],
        "videos_missing_local": counts["missing_local_video"],
        "videos_failed": counts["error"],
        "videos_resumed": sum(bool(r["reused_cache"]) for r in statuses),
        "frames_decoded": sum(int(r["frames_decoded"]) for r in statuses if r["status"] == "ok"),
        "predictions_written": sum(int(r["predictions_written"]) for r in statuses if r["status"] == "ok"),
        "untracked_detections": sum(int(r["untracked_detections"]) for r in statuses if r["status"] == "ok"),
    }
    _write_json_atomic(summary, summary_path)
    if counts["error"] or counts["missing_local_video"]:
        raise RuntimeError(
            f"Tracking inference incomplete: {counts['error']} failed video(s), "
            f"{counts['missing_local_video']} missing local video(s). "
            f"Details: {status_path}; successfully inferred videos are resumable."
        )
    if not counts["ok"]:
        raise RuntimeError(f"No completed videos to evaluate; see {status_path}")
    return summary


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run continuous YOLO/BoT-SORT tracking for each available MP4")
    p.add_argument("--eval-csv", type=Path, required=True)
    p.add_argument("--download-status-csv", type=Path, required=True)
    p.add_argument("--sequences-csv", type=Path, required=True)
    p.add_argument("--split", choices=["val", "test"], required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--tracker", required=True)
    p.add_argument("--conf", type=float, required=True)
    p.add_argument("--iou", type=float, required=True)
    p.add_argument("--imgsz", type=int, required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--cache-dir", type=Path, required=True)
    p.add_argument("--predictions-parquet", type=Path, required=True)
    p.add_argument("--inference-status-csv", type=Path, required=True)
    p.add_argument("--summary-json", type=Path, required=True)
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_argparser().parse_args(argv)
    tasks = read_tasks(args.eval_csv, args.download_status_csv, args.sequences_csv, args.split)
    summary = infer_split(
        tasks=tasks, settings=Settings(
            args.tracker, args.conf, args.iou, args.imgsz, args.device,
        ), model_path=args.model, cache_dir=args.cache_dir,
        predictions_path=args.predictions_parquet,
        status_path=args.inference_status_csv, summary_path=args.summary_json,
    )
    print("Tracking inference complete:", json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
