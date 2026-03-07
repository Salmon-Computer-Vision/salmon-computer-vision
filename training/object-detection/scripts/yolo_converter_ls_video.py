#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pyyaml>=6.0.3",
# ]
# [tool.uv]
# exclude-newer = "2026-03-02T18:41:13Z"
# ///

import yaml
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime
import io
import tarfile
import zlib

class TarShardWriter:
    def __init__(self, out_dir: Path, shard_size: int = 10000, prefix: str = "yolo_annos"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.shard_size = int(shard_size)
        self.prefix = prefix

        self._shard_idx = 0
        self._n_in_shard = 0
        self._tar = None  # tarfile.TarFile

        self._open_new()

    def _open_new(self):
        if self._tar is not None:
            self._tar.close()
        shard_name = f"{self.prefix}-{self._shard_idx:06d}.tar"
        self._tar_path = self.out_dir / shard_name
        self._tar = tarfile.open(self._tar_path, mode="w")  # uncompressed tar
        self._n_in_shard = 0
        self._shard_idx += 1

    def write_text(self, rel_path: str, text: str):
        # rotate shard if needed
        if self._n_in_shard >= self.shard_size:
            self._open_new()

        data = text.encode("utf-8")
        ti = tarfile.TarInfo(name=rel_path)
        ti.size = len(data)
        self._tar.addfile(ti, io.BytesIO(data))

        self._n_in_shard += 1

    def close(self):
        if self._tar is not None:
            self._tar.close()
            self._tar = None

def load_class_map_from_yolo_yaml(yaml_path: Path) -> Dict[str, int]:
    """
    Load a YOLO-style data.yaml and return a mapping: class_name -> class_id

    Expects something like:

      names:
        0: Coho
        1: Bull
        2: Rainbow
        ...

    or:

      names: [Coho, Bull, Rainbow, ...]
    """
    data: Any = yaml.safe_load(Path(yaml_path).read_text())
    names = data.get("names")
    if names is None:
        raise ValueError(f"'names' not found in {yaml_path}")

    class_map: Dict[str, int] = {}

    if isinstance(names, dict):
        # {0: 'Coho', 1: 'Bull', ...} (keys can be int or str)
        for k, v in names.items():
            try:
                idx = int(k)
            except Exception:
                raise ValueError(f"Invalid class index {k!r} in names of {yaml_path}")
            label = str(v)
            class_map[label] = idx
    elif isinstance(names, (list, tuple)):
        # ['Coho', 'Bull', 'Rainbow', ...]
        for idx, label in enumerate(names):
            class_map[str(label)] = idx
    else:
        raise ValueError(f"Unsupported 'names' structure in {yaml_path}: {type(names)}")

    return class_map

@dataclass
class ConvertStats:
    videos_with_boxes: int = 0
    videos_without_boxes: int = 0
    label_files_written: int = 0
    errors: int = 0

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

def _coord_mode(x: float, y: float, w: float, h: float) -> str:
    """
    Infer coordinate mode for Label Studio:
    - 'percent'   : typical LS UI export (0..100)
    - 'normalized': already 0..1
    - 'pixel'     : values > 100 (needs video width/height)
    """
    mx = max(x, y, w, h)
    if mx <= 1.0000001:       # already normalized
        return "normalized"
    if mx <= 100.0000001:     # percent
        return "percent"
    return "pixel"


def _to_yolo(
    x: float,
    y: float,
    w: float,
    h: float,
    vid_w: int,
    vid_h: int,
    forced_mode: Optional[str] = None,
) -> Tuple[float, float, float, float]:
    """
    Convert LS-style box to YOLO (xc, yc, w, h) in [0,1].

    :param forced_mode: One of {"percent", "normalized", "pixel", None/"auto"}.
                        If None or "auto", infer from values.
    """
    mode = forced_mode or "auto"
    if mode == "auto":
        mode = _coord_mode(x, y, w, h)

    if mode == "normalized":
        xc = x + w / 2.0
        yc = y + h / 2.0
        wn = w
        hn = h
    elif mode == "percent":
        xc = (x + w / 2.0) / 100.0
        yc = (y + h / 2.0) / 100.0
        wn = w / 100.0
        hn = h / 100.0
    elif mode == "pixel":
        xc = (x + w / 2.0) / float(vid_w) if vid_w else 0.0
        yc = (y + h / 2.0) / float(vid_h) if vid_h else 0.0
        wn = w / float(vid_w) if vid_w else 0.0
        hn = h / float(vid_h) if vid_h else 0.0
    else:
        raise ValueError(f"Unknown coord_mode: {forced_mode!r}")

    # clamp to [0,1]
    xc = min(max(xc, 0.0), 1.0)
    yc = min(max(yc, 0.0), 1.0)
    wn = min(max(wn, 0.0), 1.0)
    hn = min(max(hn, 0.0), 1.0)
    return xc, yc, wn, hn


class YoloConverterLSVideo:
    """
    Convert the provided Label Studio 'video' export (annotations + data) to YOLO frame txts.

    Input structure:
    [
      {
        "data": {
          "metadata_video_width": 1280,
          "metadata_video_height": 720,
          "video": "s3://.../GOLD-kitkiata-jetson-1_20240720_002007_M.mp4",
          "metadata_file_filename": "GOLD-kitkiata-jetson-1_20240720_002007_M.mp4",
          ...
        },
        "annotations": [
          {
            "result": [
              {
                "type": "videorectangle",
                "from_name": "box",
                "to_name": "video",
                "value": {
                  "labels": ["Rainbow"],
                  "sequence": [
                    {"frame": 47, "x": 0, "y": 62.83, "width": 15.96, "height": 15.16, "enabled": true, ...},
                    ...
                  ]
                }
              },
              ...
            ]
          }
        ]
      },
      {
        ...
      },
      ...
    ]

    Writes:
      <out_dir>/<video_stem>/frame_000047.txt  # one line per box in that frame
    """

    def __init__(
        self,
        class_map: Dict[str, int],
        output_dir: Path,
        empty_list_path: Optional[Path] = None,
        overwrite_video_dir: bool = False,
        result_type: str = "videorectangle",
        from_name: Optional[str] = None,  # e.g., "box"; if None accept any
        to_name: Optional[str] = None,    # e.g., "video"; if None accept any
        coord_mode: str = "auto",         # "auto", "percent", "normalized", "pixel"
        error_log_path: Optional[Path] = None,
        include_sites: List[str] = [],
        shard_dir: Optional[Path] = None,
        shard_size: int = 10000,
        frame_stride: int = 1,
        frame_offset_mode: str = "fixed",
        frame_offset: int = 0,
    ):
        """
        :param coord_mode:
            "auto"       -> infer (default)
            "percent"    -> x/y/width/height are 0..100
            "normalized" -> x/y/width/height are 0..1
            "pixel"      -> x/y/width/height are in pixels
        :param error_log_path: where to append error tracebacks.
                           If None, defaults to <output_dir>/ls_to_yolo_errors.log
        """
        self.class_map = class_map
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.empty_list_path = Path(empty_list_path) if empty_list_path else None
        self.overwrite_video_dir = overwrite_video_dir
        self.result_type = result_type
        self.from_name = from_name
        self.to_name = to_name
        self.coord_mode = coord_mode
        self.error_log_path = (
            Path(error_log_path) if error_log_path else (self.output_dir / "ls_to_yolo_errors.log")
        )
        self.include_sites = include_sites
        self.shard_dir = Path(shard_dir) if shard_dir else None
        self.shard_size = int(shard_size)
        self._sharder = TarShardWriter(self.shard_dir, shard_size=self.shard_size) if self.shard_dir else None
        self.frame_stride = max(1, int(frame_stride))
        self.frame_offset_mode = frame_offset_mode
        self.frame_offset = int(frame_offset)

    # ---- public API ----

    def convert_folder(self, json_dir: Path, pattern: str = "*.json") -> ConvertStats:
        stats = ConvertStats()
        for p in sorted(Path(json_dir).glob(pattern)):
            try:
                s = self.convert_file(p)
                stats.videos_with_boxes += s.videos_with_boxes
                stats.videos_without_boxes += s.videos_without_boxes
                stats.label_files_written += s.label_files_written
            except Exception as e:
                stats.errors += 1
                self._log_error(f"convert_file({p})", e)
        return stats

    def convert_file(self, json_path: Path) -> ConvertStats:
        stats = ConvertStats()
        json_path = Path(json_path)

        try:
            items = json.loads(json_path.read_text())
        except Exception as e:
            stats.errors += 1
            self._log_error(f"read_json({json_path})", e)
            return stats

        if not isinstance(items, list):
            err = ValueError(f"{json_path} must contain a top-level list")
            stats.errors += 1
            self._log_error(f"validate_json({json_path})", err)
            return stats

        for item in items:
            try:
                s = self._convert_item(item)
                stats.videos_with_boxes += s.videos_with_boxes
                stats.videos_without_boxes += s.videos_without_boxes
                stats.label_files_written += s.label_files_written
            except Exception as e:
                stats.errors += 1
                item_id = item.get("id", "unknown")
                self._log_error(f"_convert_item(id={item_id}, src={json_path})", e)
        return stats

    # ---- internals ----

    def _stride_offset(self, video_stem: str) -> int:
        if self.frame_stride <= 1:
            return 0
        if self.frame_offset_mode == "fixed":
            return int(self.frame_offset) % self.frame_stride
        if self.frame_offset_mode == "video_hash":
            # deterministic across runs + platforms
            return zlib.crc32(video_stem.encode("utf-8")) % self.frame_stride

        raise ValueError("Invalid frame offset mode")

    @staticmethod
    def _interpolate_sequence(seq: Iterable[dict]) -> Dict[int, List[Tuple[float, float, float, float]]]:
        """
        Given a Label Studio 'sequence' (list of keyframes) like:

          {
            "frame": 47, "x": 0, "y": 62.8, "width": 15.9, "height": 15.1, "enabled": true
          },
          ...

        Produce: frame_index -> list of (x, y, w, h) in the SAME units as input.

        Semantics:
        - Every keyframe (enabled or not) produces a box at its own frame.
        - If a keyframe has enabled=True, we linearly interpolate boxes for the frames
          *between it and the next keyframe* (f0+1 .. f1-1).
        - If a keyframe has enabled=False, we do NOT interpolate forward from it,
          but we still keep its own box at that frame.
        - A disabled keyframe can still be the *end* of an interpolation that started
          from a previous enabled keyframe (since that interpolation uses the previous
          keyframe's enabled flag).
        """
        # Sort keyframes by frame
        kfs = sorted(seq, key=lambda k: int(_safe_float(k.get("frame"), 0)))
        frames_boxes: Dict[int, List[Tuple[float, float, float, float]]] = {}

        if not kfs:
            return frames_boxes

        # 1) Add all keyframes as boxes at their exact frames
        for k in kfs:
            f = int(_safe_float(k.get("frame"), -1))
            if f < 0:
                continue

            x = _safe_float(k.get("x"))
            y = _safe_float(k.get("y"))
            w = _safe_float(k.get("width"))
            h = _safe_float(k.get("height"))
            frames_boxes.setdefault(f, []).append((x, y, w, h))

        # 2) Interpolate between consecutive keyframes when the *start* keyframe is enabled
        for i in range(len(kfs) - 1):
            k0 = kfs[i]
            k1 = kfs[i + 1]

            f0 = int(_safe_float(k0.get("frame"), -1))
            f1 = int(_safe_float(k1.get("frame"), -1))
            if f0 < 0 or f1 <= f0:
                continue

            enabled0 = bool(k0.get("enabled", True))
            if not enabled0:
                # Do not interpolate forward from a disabled keyframe
                continue

            x0 = _safe_float(k0.get("x"))
            y0 = _safe_float(k0.get("y"))
            w0 = _safe_float(k0.get("width"))
            h0 = _safe_float(k0.get("height"))

            x1 = _safe_float(k1.get("x"))
            y1 = _safe_float(k1.get("y"))
            w1 = _safe_float(k1.get("width"))
            h1 = _safe_float(k1.get("height"))

            # Fill in strictly between endpoints; endpoints themselves are already added
            for f in range(f0 + 1, f1):
                t = (f - f0) / float(f1 - f0)
                x = x0 + (x1 - x0) * t
                y = y0 + (y1 - y0) * t
                w = w0 + (w1 - w0) * t
                h = h0 + (h1 - h0) * t
                frames_boxes.setdefault(f, []).append((x, y, w, h))

        return frames_boxes

    def _log_error(self, context: str, exc: Exception):
        try:
            self.error_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.error_log_path.open("a") as f:
                f.write(f"\n=== ERROR in {context} ===\n")
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
        except Exception:
            # last-resort: don't crash because logging failed
            pass

    @staticmethod
    def _parse_ts(s):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def _convert_item(self, item: dict) -> ConvertStats:
        stats = ConvertStats()

        data = item.get("data") or {}
        site = data.get("metadata_file_site_reference_string") or ""
        if len(self.include_sites) > 0:
            if site not in self.include_sites:
                # Not in included sites
                return stats

        video_uri = data.get("metadata_file_filename") or data.get("video") or "unknown.mp4"
        video_stem = Path(video_uri).stem
        vid_w = int(_safe_float(data.get("metadata_video_width"), 0))
        vid_h = int(_safe_float(data.get("metadata_video_height"), 0))

        annos = item.get("annotations") or []
        results = []
        if len(annos) > 0:
            latest_ann = max(
                annos,
                key=lambda a: YoloConverterLSVideo._parse_ts(a["updated_at"])
            )

            for r in (latest_ann.get("result") or []):
                if r.get("type") != self.result_type:
                    continue
                if self.from_name is not None and r.get("from_name") != self.from_name:
                    continue
                if self.to_name is not None and r.get("to_name") != self.to_name:
                    continue
                results.append(r)

        wrote_any = False

        # Collect lines per frame
        frame_lines: Dict[int, List[str]] = defaultdict(list)
        for r in results:
            value = r.get("value") or {}
            labels: List[str] = value.get("labels") or []
            if not labels:
                continue
            cls_name = labels[0]
            if cls_name not in self.class_map:
                # unknown class; skip this track
                continue
            cls_id = self.class_map[cls_name]

            seq: Iterable[dict] = value.get("sequence") or []
            frame_boxes = self._interpolate_sequence(seq)  # frame -> [(x,y,w,h), ...]

            for frame_idx, boxes in frame_boxes.items():
                for (x, y, w, h) in boxes:
                    xc, yc, wn, hn = _to_yolo(
                        x, y, w, h,
                        vid_w=vid_w,
                        vid_h=vid_h,
                        forced_mode=self.coord_mode,
                    )
                    frame_lines[frame_idx].append(f"{cls_id} {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}")
                    wrote_any = True

        if wrote_any:
            stats.videos_with_boxes += 1
        else:
            stats.videos_without_boxes += 1
            if self.empty_list_path:
                with self.empty_list_path.open("a") as f:
                    f.write(f"{video_uri}\n")

        # Apply frame sampling
        if self.frame_stride > 1 and frame_lines:
            off = self._stride_offset(video_stem)
            frame_lines = {f: lines for f, lines in frame_lines.items()
                           if (f % self.frame_stride) == off}

        stats.label_files_written += len(frame_lines)
        if self._sharder:
            # write into shards: <video_stem>/frame_000123.txt
            for frame_idx, lines in frame_lines.items():
                rel_path = f"{video_stem}/frame_{frame_idx:06d}.txt"
                self._sharder.write_text(rel_path, "\n".join(lines) + "\n")
        else:
            # current behavior: write to filesystem
            vid_dir = self.output_dir / video_stem

            if vid_dir.exists() and not self.overwrite_video_dir:
                # skip existing video dir to avoid mixing runs
                return stats
            vid_dir.mkdir(parents=True, exist_ok=True)

            for frame_idx, lines in frame_lines.items():
                label_path = vid_dir / f"frame_{frame_idx:06d}.txt"
                label_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.write_text("\n".join(lines) + "\n")

        return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert Label Studio video JSON to YOLO frame labels")
    parser.add_argument("input", help="JSON file or directory containing Label Studio JSON")
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
    args = parser.parse_args()

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
    )

    inp = Path(args.input)
    if inp.is_dir():
        print(f"Converting labels from {inp}")

        s = conv.convert_folder(inp, pattern=args.pattern)
    else:
        s = conv.convert_file(inp)

    if getattr(conv, "_sharder", None):
        conv._sharder.close()

    print(
        f"Done. with_boxes={s.videos_with_boxes} without_boxes={s.videos_without_boxes} "
        f"labels_written={s.label_files_written} errors={s.errors}"
    )
