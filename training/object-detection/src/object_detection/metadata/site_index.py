from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SITE_FIELD = "metadata_file_site_reference_string"
ORG_FIELD = "metadata_file_organization_reference_string"
CAMERA_FIELD = "metadata_file_camera_reference_string"


@dataclass(frozen=True)
class SiteFileRecord:
    path: str
    sha256: str
    task_count: int
    total_tasks: int
    organizations: list[str]
    cameras: list[str]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def iter_tasks(obj) -> Iterable[dict]:
    """
    Label Studio exports are normally top-level lists of tasks.

    Also tolerate a single-task dict or a dict containing `tasks`.
    """
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
        return

    if isinstance(obj, dict):
        tasks = obj.get("tasks")

        if isinstance(tasks, list):
            for item in tasks:
                if isinstance(item, dict):
                    yield item
            return

        # Treat as one task if it resembles a Label Studio task.
        if "data" in obj:
            yield obj


def inspect_export(
    path: Path,
    *,
    raw_root: Path,
) -> tuple[dict[str, SiteFileRecord], int]:
    """
    Return records keyed by site.

    A JSON export containing more than one site is supported: the same source
    file will appear in multiple site manifests with the site-specific
    task_count.

    Returns:
        records_by_site
        number_of_tasks_missing_site_metadata
    """
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    tasks = list(iter_tasks(obj))
    total_tasks = len(tasks)

    counts: Counter[str] = Counter()
    orgs: dict[str, set[str]] = defaultdict(set)
    cameras: dict[str, set[str]] = defaultdict(set)

    missing_site = 0

    for task in tasks:
        data = task.get("data") or {}

        site = data.get(SITE_FIELD)
        if site is None or not str(site).strip():
            missing_site += 1
            continue

        site = str(site).strip()

        counts[site] += 1

        org = data.get(ORG_FIELD)
        if org is not None and str(org).strip():
            orgs[site].add(str(org).strip())

        camera = data.get(CAMERA_FIELD)
        if camera is not None and str(camera).strip():
            cameras[site].add(str(camera).strip())

    if not counts:
        return {}, missing_site

    digest = sha256_file(path)

    try:
        relative_path = path.relative_to(raw_root)
    except ValueError:
        relative_path = path

    result: dict[str, SiteFileRecord] = {}

    for site, count in counts.items():
        result[site] = SiteFileRecord(
            path=str(relative_path),
            sha256=digest,
            task_count=count,
            total_tasks=total_tasks,
            organizations=sorted(orgs[site]),
            cameras=sorted(cameras[site]),
        )

    return result, missing_site


def safe_site_filename(site: str) -> str:
    """
    Keep site names human-readable but prevent path traversal / bad filenames.
    """
    site = site.strip()

    if not site:
        raise ValueError("Empty site name")

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", site)


def build_site_index(
    *,
    raw_root: Path,
    out_dir: Path,
    pattern: str = "**/*.json",
    allowed_sites: set[str] | None = None,
) -> dict:
    """
    Scan all Label Studio exports and write one deterministic manifest per site.

    The manifests deliberately contain no generation timestamp so unchanged
    sites produce byte-for-byte identical files across runs.
    """
    if not raw_root.exists():
        raise FileNotFoundError(raw_root)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale manifests from an earlier indexing run.
    for old in out_dir.glob("*.json"):
        old.unlink()

    site_records: dict[str, list[SiteFileRecord]] = defaultdict(list)

    json_files_seen = 0
    tasks_missing_site = 0
    files_without_site = 0

    for json_path in sorted(raw_root.glob(pattern)):
        if not json_path.is_file():
            continue

        json_files_seen += 1

        records, missing = inspect_export(
            json_path,
            raw_root=raw_root,
        )

        tasks_missing_site += missing

        if not records:
            files_without_site += 1
            continue

        for site, record in records.items():
            if allowed_sites is not None and site not in allowed_sites:
                continue

            site_records[site].append(record)

    site_summaries = {}

    for site in sorted(site_records):
        records = sorted(
            site_records[site],
            key=lambda r: r.path,
        )

        manifest = {
            "site": site,
            "raw_root": str(raw_root),
            "file_count": len(records),
            "task_count": sum(r.task_count for r in records),
            "files": [asdict(r) for r in records],
        }

        filename = safe_site_filename(site) + ".json"
        out_path = out_dir / filename

        out_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        site_summaries[site] = {
            "manifest": filename,
            "file_count": len(records),
            "task_count": manifest["task_count"],
        }

    summary = {
        "raw_root": str(raw_root),
        "json_files_seen": json_files_seen,
        "site_count": len(site_records),
        "tasks_missing_site": tasks_missing_site,
        "files_without_site": files_without_site,
        "sites": site_summaries,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return summary
