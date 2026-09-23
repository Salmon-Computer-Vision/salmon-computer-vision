#!/usr/bin/env -S uv run python

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from object_detection.dataset.merge import (
    merge_packed_csvs,
    merge_site_manifests,
)


def main() -> None:
    p = argparse.ArgumentParser()

    p.add_argument("--sites-root", required=True, type=Path)
    p.add_argument("--manifests-root", required=True, type=Path)
    p.add_argument("--data-yaml", required=True, type=Path)
    p.add_argument("--manifest-csv", required=True, type=Path)

    p.add_argument(
        "--params-yaml",
        type=Path,
        default=Path("params.yaml"),
    )

    args = p.parse_args()

    params = yaml.safe_load(
        args.params_yaml.read_text(encoding="utf-8")
    )

    sites = params["data"]["sites"]

    if not isinstance(sites, list):
        raise ValueError(
            "params.yaml data.sites must be a YAML list for foreach"
        )

    sites = [str(site) for site in sites]

    merge_site_manifests(
        sites_root=args.sites_root,
        sites=sites,
        manifests_root=args.manifests_root,
        data_yaml=args.data_yaml,
    )

    merge_packed_csvs(
        sites_root=args.sites_root,
        sites=sites,
        out_csv=args.manifest_csv,
    )

    print(f"Merged {len(sites)} packed site datasets:")
    for site in sites:
        print(f"  {site}")


if __name__ == "__main__":
    main()
