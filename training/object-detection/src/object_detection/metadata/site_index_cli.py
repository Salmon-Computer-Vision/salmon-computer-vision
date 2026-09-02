from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.metadata.site_index import build_site_index


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Index Label Studio JSON exports by "
            "metadata_file_site_reference_string."
        )
    )

    parser.add_argument(
        "--json-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--pattern",
        default="**/*.json",
    )
    parser.add_argument(
        "--sites",
        nargs="*",
        default=None,
        help=(
            "Optional allowed site list. When omitted, index every site "
            "found in the exports."
        ),
    )

    args = parser.parse_args()

    summary = build_site_index(
        raw_root=args.json_root,
        out_dir=args.out_dir,
        pattern=args.pattern,
        allowed_sites=set(args.sites) if args.sites else None,
    )

    print(
        f"Indexed {summary['json_files_seen']} JSON files "
        f"into {summary['site_count']} sites"
    )

    for site, info in sorted(summary["sites"].items()):
        print(
            f"  {site}: "
            f"{info['file_count']} export(s), "
            f"{info['task_count']} task(s)"
        )

    if summary["tasks_missing_site"]:
        print(
            f"WARNING: {summary['tasks_missing_site']} tasks were missing "
            "metadata_file_site_reference_string"
        )

    if summary["files_without_site"]:
        print(
            f"WARNING: {summary['files_without_site']} JSON files had no "
            "usable site metadata"
        )


if __name__ == "__main__":
    main()
