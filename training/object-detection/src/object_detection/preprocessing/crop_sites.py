from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2

from object_detection.utils.utils import parse_video_stem


IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class CropSummary:
    dataset_root: str
    sites: List[str]
    crop: str
    images_seen: int = 0
    images_cropped: int = 0
    images_skipped_site: int = 0
    images_failed: int = 0
    labels_seen: int = 0
    labels_rewritten: int = 0
    label_lines_before: int = 0
    label_lines_after: int = 0
    boxes_dropped: int = 0


def _iter_images(dataset_root: Path, split_names: Sequence[str]) -> Iterable[Path]:
    for split in split_names:
        split_dir = dataset_root / split
        if not split_dir.exists():
            continue

        for p in split_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                yield p


def _site_from_image_path(image_path: Path) -> Optional[str]:
    """
    Expected layout:
      <dataset_root>/<split>/<video_stem>/frame_000123.jpg
    """
    video_stem = image_path.parent.name
    meta = parse_video_stem(video_stem)
    if meta is None:
        return None
    return meta.get("site")


def _read_yolo_lines(label_path: Path) -> List[str]:
    if not label_path.exists():
        return []
    text = label_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _write_yolo_lines(label_path: Path, lines: Sequence[str]) -> None:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _transform_yolo_line_top_half(
    line: str,
    *,
    crop_y0: float = 0.0,
    crop_y1: float = 0.5,
    min_visible_frac: float = 0.05,
) -> Optional[str]:
    """
    Transform one YOLO detection line for a vertical crop.

    Original coordinates are normalized to full image:
      cls xc yc w h

    Top-half crop keeps normalized y interval [0.0, 0.5].
    New image height is half the original, so y values are remapped by:
      y_new = (y_old - crop_y0) / (crop_y1 - crop_y0)

    Boxes fully outside the crop are dropped. Boxes crossing the crop
    boundary are clipped.
    """
    parts = line.split()
    if len(parts) < 5:
        return None

    cls = parts[0]
    extras = parts[5:]

    try:
        xc = float(parts[1])
        yc = float(parts[2])
        bw = float(parts[3])
        bh = float(parts[4])
    except ValueError:
        return None

    x1 = xc - bw / 2.0
    y1 = yc - bh / 2.0
    x2 = xc + bw / 2.0
    y2 = yc + bh / 2.0

    # Clamp to original image bounds first.
    x1 = max(0.0, min(1.0, x1))
    x2 = max(0.0, min(1.0, x2))
    y1 = max(0.0, min(1.0, y1))
    y2 = max(0.0, min(1.0, y2))

    old_w = max(0.0, x2 - x1)
    old_h = max(0.0, y2 - y1)
    old_area = old_w * old_h
    if old_area <= 0:
        return None

    # Clip to crop region.
    cy1 = max(y1, crop_y0)
    cy2 = min(y2, crop_y1)

    if cy2 <= cy1:
        return None

    visible_area = old_w * (cy2 - cy1)
    visible_frac = visible_area / old_area if old_area > 0 else 0.0
    if visible_frac < min_visible_frac:
        return None

    crop_h = crop_y1 - crop_y0

    new_x1 = x1
    new_x2 = x2
    new_y1 = (cy1 - crop_y0) / crop_h
    new_y2 = (cy2 - crop_y0) / crop_h

    new_xc = (new_x1 + new_x2) / 2.0
    new_yc = (new_y1 + new_y2) / 2.0
    new_bw = new_x2 - new_x1
    new_bh = new_y2 - new_y1

    # Final sanity clamp.
    new_xc = max(0.0, min(1.0, new_xc))
    new_yc = max(0.0, min(1.0, new_yc))
    new_bw = max(0.0, min(1.0, new_bw))
    new_bh = max(0.0, min(1.0, new_bh))

    if new_bw <= 0 or new_bh <= 0:
        return None

    out = f"{cls} {new_xc:.6f} {new_yc:.6f} {new_bw:.6f} {new_bh:.6f}"
    if extras:
        out += " " + " ".join(extras)
    return out


def rewrite_label_for_top_half(
    label_path: Path,
    *,
    min_visible_frac: float = 0.05,
) -> Tuple[int, int]:
    old_lines = _read_yolo_lines(label_path)
    new_lines: List[str] = []

    for line in old_lines:
        new_line = _transform_yolo_line_top_half(
            line,
            crop_y0=0.0,
            crop_y1=0.5,
            min_visible_frac=min_visible_frac,
        )
        if new_line is not None:
            new_lines.append(new_line)

    _write_yolo_lines(label_path, new_lines)
    return len(old_lines), len(new_lines)


def crop_image_top_half_in_place(image_path: Path) -> None:
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cv2.imread failed: {image_path}")

    h, w = img.shape[:2]
    if h < 2:
        raise RuntimeError(f"Image height too small to crop: {image_path} height={h}")

    crop_h = h // 2
    cropped = img[:crop_h, :, :]

    ext = image_path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        ok = cv2.imwrite(str(image_path), cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
    elif ext == ".png":
        ok = cv2.imwrite(str(image_path), cropped, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    else:
        ok = cv2.imwrite(str(image_path), cropped)

    if not ok:
        raise RuntimeError(f"cv2.imwrite failed: {image_path}")


def crop_sites_top_half(
    *,
    dataset_root: Path,
    sites: Sequence[str],
    split_names: Sequence[str] = ("train", "val", "test"),
    min_visible_frac: float = 0.05,
    summary_json: Optional[Path] = None,
) -> CropSummary:
    sites_set = set(sites)

    summary = CropSummary(
        dataset_root=str(dataset_root),
        sites=sorted(sites_set),
        crop="top_half",
    )

    for image_path in _iter_images(dataset_root, split_names):
        summary.images_seen += 1

        site = _site_from_image_path(image_path)
        if site not in sites_set:
            summary.images_skipped_site += 1
            continue

        label_path = image_path.with_suffix(".txt")

        try:
            if label_path.exists():
                summary.labels_seen += 1
                before, after = rewrite_label_for_top_half(
                    label_path,
                    min_visible_frac=min_visible_frac,
                )
                summary.label_lines_before += before
                summary.label_lines_after += after
                summary.boxes_dropped += max(0, before - after)
                summary.labels_rewritten += 1
            else:
                # YOLO allows missing labels in some workflows, but your packed
                # dataset should normally have a txt file beside every image.
                _write_yolo_lines(label_path, [])
                summary.labels_seen += 1
                summary.labels_rewritten += 1

            crop_image_top_half_in_place(image_path)
            summary.images_cropped += 1

        except Exception as e:
            summary.images_failed += 1
            print(f"[WARN] Failed to crop {image_path}: {e}")

    if summary_json is not None:
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(
            json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return summary
