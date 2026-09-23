from __future__ import annotations

import argparse
from pathlib import Path

from object_detection.metadata.filter import filter_metadata_csv_by_site


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a video metadata index to one site."
    )

    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--site", required=True)
    parser.add_argument("--out-csv", required=True, type=Path)

    args = parser.parse_args()

    n = filter_metadata_csv_by_site(
        input_csv=args.input_csv,
        site=args.site,
        out_csv=args.out_csv,
    )

    print(
        f"Wrote {n} metadata rows for site {args.site!r} "
        f"to {args.out_csv}"
    )


if __name__ == "__main__":
    main()
