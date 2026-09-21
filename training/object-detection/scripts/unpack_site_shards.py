#!/usr/bin/env -S uv run python

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()

    p.add_argument("--sites-root", required=True, type=Path)
    p.add_argument("--active-sites-file", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument(
        "--unpack-script",
        type=Path,
        default=Path("scripts/unpack_annos.sh"),
    )

    args = p.parse_args()

    sites = [
        line.strip()
        for line in args.active_sites_file.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for site in sites:
        shards = args.sites_root / site / "shards"

        if not shards.exists():
            raise FileNotFoundError(
                f"Missing shards for site {site!r}: {shards}"
            )

        print(f"Unpacking {site}: {shards}")

        subprocess.run(
            [
                str(args.unpack_script),
                str(shards),
                str(args.out_dir),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
