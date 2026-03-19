import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime
import random
import zlib

from object_detection.yolo_ls.shards import TarShardWriter
from object_detection.yolo_ls.parsing import (
    coord_mode,
    safe_float,
    to_yolo,
)

@dataclass
class ConvertStats:
    videos_with_boxes: int = 0
    videos_without_boxes: int = 0
    label_lines_written: int = 0      # box lines
    label_files_written: int = 0      # positive frame txt files
    negative_files_written: int = 0   # negative frame txt files
    total_candidate_negative_frames: int = 0   # total candidate negative frames
    errors: int = 0

@dataclass
class NegativeVideoCandidate:
    video_stem: str
    video_uri: str
    total_frames: int

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
        include_sites: Optional[List[str]] = None,
        shard_dir: Optional[Path] = None,
        shard_size: int = 10000,
        frame_stride: int = 1,
        frame_offset_mode: str = "fixed",
        frame_offset: int = 0,
        include_negatives: bool = False,
        negative_ratio: float = 0.10,
        negatives_per_video: int = 6,
        negative_seed: int = 42,
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
        self.include_sites = include_sites or []
        self.shard_dir = Path(shard_dir) if shard_dir else None
        self.shard_size = int(shard_size)
        self._sharder = TarShardWriter(self.shard_dir, shard_size=self.shard_size) if self.shard_dir else None
        self.frame_stride = max(1, int(frame_stride))
        self.frame_offset_mode = frame_offset_mode
        self.frame_offset = int(frame_offset)

        self.include_negatives = include_negatives
        self.negative_ratio = float(negative_ratio)
        self.negatives_per_video = int(negatives_per_video)
        self.negative_seed = int(negative_seed)

        self._positive_frame_files_written = 0
        self._negative_frame_files_written = 0
        self._negative_candidates: List[NegativeVideoCandidate] = []

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

    def materialize_negatives(self) -> Tuple[int, int]:
        """
        Sample negatives globally so negatives are at most self.negative_ratio
        of the final dataset. Returns number of negative files written.
        """
        if not self.include_negatives:
            return 0, 0

        pos = self._positive_frame_files_written
        if pos <= 0:
            return 0, 0

        r = self.negative_ratio
        if r <= 0:
            return 0, 0
        if r >= 1:
            max_neg = sum(
                min(self.negatives_per_video, len(self._eligible_frames_for_video(c.video_stem, c.total_frames)))
                for c in self._negative_candidates
            )
        else:
            max_neg = int((r / (1.0 - r)) * pos)

        if max_neg <= 0:
            return 0, 0

        # Build all candidates at the video level first
        per_video_samples: Dict[str, List[int]] = {}
        total_candidate_frames = 0

        for c in self._negative_candidates:
            eligible = self._eligible_frames_for_video(c.video_stem, c.total_frames)
            if not eligible:
                continue

            k = min(self.negatives_per_video, len(eligible))
            sampled = self._sample_negative_frames_for_video(c.video_stem, c.total_frames, k)
            if sampled:
                per_video_samples[c.video_stem] = sampled
                total_candidate_frames += len(sampled)

        if total_candidate_frames <= 0:
            return 0, total_candidate_frames

        # Flatten candidates, then globally subsample if needed
        flat: List[Tuple[str, int]] = []
        for video_stem, frames in per_video_samples.items():
            for frame_idx in frames:
                flat.append((video_stem, frame_idx))

        # Deterministic global shuffle
        flat.sort()
        rng = random.Random(self.negative_seed)
        rng.shuffle(flat)

        flat = flat[:max_neg]

        # Write empty labels
        wrote = 0
        for video_stem, frame_idx in sorted(flat):
            self._write_label(video_stem, frame_idx, "")
            wrote += 1

        self._negative_frame_files_written += wrote
        return wrote, total_candidate_frames

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
    def _parse_ffmpeg_rate(rate: Any) -> float:
        """
        Parse strings like '10/1' or '30000/1001' into float.
        """
        if rate is None:
            return 0.0
        if isinstance(rate, (int, float)):
            return float(rate)

        s = str(rate).strip()
        if "/" in s:
            a, b = s.split("/", 1)
            try:
                num = float(a)
                den = float(b)
                return num / den if den else 0.0
            except Exception:
                return 0.0
        try:
            return float(s)
        except Exception:
            return 0.0


    def _infer_total_frames(self, item: dict, results: Optional[List[dict]] = None) -> int:
        """
        Prefer metadata_video_nb_frames. Fall back to framesCount in result.value,
        then duration * fps.
        """
        data = item.get("data") or {}

        # 1) Best source
        n = int(safe_float(data.get("metadata_video_nb_frames"), 0))
        if n > 0:
            return n

        # 2) From result.value.framesCount
        if results:
            for r in results:
                value = r.get("value") or {}
                n = int(safe_float(value.get("framesCount"), 0))
                if n > 0:
                    return n

        # 3) duration * fps
        duration = safe_float(
            data.get("metadata_video_duration",
                     data.get("duration", 0.0)),
            0.0
        )

        fps = safe_float(data.get("frames_per_second"), 0.0)
        if fps <= 0:
            fps = self._parse_ffmpeg_rate(data.get("metadata_video_r_frame_rate"))
        if fps <= 0:
            fps = self._parse_ffmpeg_rate(data.get("metadata_video_avg_frame_rate"))

        if duration > 0 and fps > 0:
            return int(round(duration * fps))

        return 0


    def _eligible_frames_for_video(self, video_stem: str, total_frames: int) -> List[int]:
        off = self._stride_offset(video_stem)
        return [f for f in range(total_frames) if (f % self.frame_stride) == off]


    def _write_empty_label(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("")

    def _write_label(self, video_stem: str, frame_idx: int, text: str):
        rel_path = f"{video_stem}/frame_{frame_idx:06d}.txt"

        if self._sharder is not None:
            self._sharder.write_text(rel_path, text)
        else:
            label_path = self.output_dir / rel_path
            label_path.parent.mkdir(parents=True, exist_ok=True)
            label_path.write_text(text)

    def _sample_negative_frames_for_video(self, video_stem: str, total_frames: int, k: int) -> List[int]:
        eligible = self._eligible_frames_for_video(video_stem, total_frames)
        if not eligible or k <= 0:
            return []

        seed = zlib.crc32(f"{video_stem}|{self.negative_seed}".encode("utf-8"))
        rng = random.Random(seed)

        if k >= len(eligible):
            return sorted(eligible)

        return sorted(rng.sample(eligible, k))

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
        kfs = sorted(seq, key=lambda k: int(safe_float(k.get("frame"), 0)))
        frames_boxes: Dict[int, List[Tuple[float, float, float, float]]] = {}

        if not kfs:
            return frames_boxes

        # 1) Add all keyframes as boxes at their exact frames
        for k in kfs:
            f = int(safe_float(k.get("frame"), -1))
            if f < 0:
                continue

            x = safe_float(k.get("x"))
            y = safe_float(k.get("y"))
            w = safe_float(k.get("width"))
            h = safe_float(k.get("height"))
            frames_boxes.setdefault(f, []).append((x, y, w, h))

        # 2) Interpolate between consecutive keyframes when the *start* keyframe is enabled
        for i in range(len(kfs) - 1):
            k0 = kfs[i]
            k1 = kfs[i + 1]

            f0 = int(safe_float(k0.get("frame"), -1))
            f1 = int(safe_float(k1.get("frame"), -1))
            if f0 < 0 or f1 <= f0:
                continue

            enabled0 = bool(k0.get("enabled", True))
            if not enabled0:
                # Do not interpolate forward from a disabled keyframe
                continue

            x0 = safe_float(k0.get("x"))
            y0 = safe_float(k0.get("y"))
            w0 = safe_float(k0.get("width"))
            h0 = safe_float(k0.get("height"))

            x1 = safe_float(k1.get("x"))
            y1 = safe_float(k1.get("y"))
            w1 = safe_float(k1.get("width"))
            h1 = safe_float(k1.get("height"))

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
        vid_w = int(safe_float(data.get("metadata_video_width"), 0))
        vid_h = int(safe_float(data.get("metadata_video_height"), 0))

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
                    xc, yc, wn, hn = to_yolo(
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
                self.empty_list_path.parent.mkdir(parents=True, exist_ok=True)
                with self.empty_list_path.open("a") as f:
                    f.write(f"{video_uri}\n")

            if self.include_negatives:
                total_frames = self._infer_total_frames(item, results=None)
                if total_frames > 0:
                    self._negative_candidates.append(
                        NegativeVideoCandidate(
                            video_stem=video_stem,
                            video_uri=video_uri,
                            total_frames=total_frames,
                        )
                    )

        # Apply frame sampling
        if self.frame_stride > 1 and frame_lines:
            off = self._stride_offset(video_stem)
            frame_lines = {f: lines for f, lines in frame_lines.items()
                           if (f % self.frame_stride) == off}

        stats.label_files_written += len(frame_lines)
        self._positive_frame_files_written += len(frame_lines)
        if self._sharder is None:
            # write to filesystem
            vid_dir = self.output_dir / video_stem

            if vid_dir.exists() and not self.overwrite_video_dir:
                # skip existing video dir to avoid mixing runs
                return stats
            vid_dir.mkdir(parents=True, exist_ok=True)

        for frame_idx, lines in frame_lines.items():
            self._write_label(video_stem, frame_idx, "\n".join(lines) + "\n")

        return stats

