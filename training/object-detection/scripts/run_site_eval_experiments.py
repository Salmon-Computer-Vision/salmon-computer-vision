#!/usr/bin/env -S uv run python
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, List, Sequence

import yaml


def run_cmd(cmd: Sequence[str], dry_run: bool = False) -> None:
    print("+ " + " ".join(shlex.quote(str(c)) for c in cmd), flush=True)
    if not dry_run:
        subprocess.run(list(cmd), check=True)


def normalize_sites(value: Any) -> List[str]:
    """
    Accepts:
      - "tankeeah kitwanga bear"
      - "tankeeah,kitwanga,bear"
      - ["tankeeah", "kitwanga", "bear"]
    """
    if value is None:
        return []

    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]

    text = str(value).strip()
    if not text:
        return []

    return [x for x in re.split(r"[\s,]+", text) if x]


def load_default_test_sites(params_yaml: Path) -> List[str]:
    data = yaml.safe_load(params_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid params YAML: {params_yaml}")

    exp = data.get("exp", {})
    if not isinstance(exp, dict):
        raise ValueError(f"'exp' section missing or invalid in {params_yaml}")

    return normalize_sites(exp.get("test_sites"))


def sanitize_exp_name(site: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", site)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Run DVC evaluation experiments once per exp.test_sites site."
    )
    p.add_argument(
        "--params-yaml",
        default="params.yaml",
        type=Path,
        help="Path to params.yaml. Defaults to params.yaml",
    )
    p.add_argument(
        "--sites",
        nargs="*",
        default=None,
        help="Sites to evaluate. Defaults to exp.test_sites from params.yaml.",
    )
    p.add_argument(
        "--target",
        default="evaluate",
        help="DVC target stage. Defaults to evaluate.",
    )
    p.add_argument(
        "--queue",
        action="store_true",
        help="Queue experiments instead of running immediately.",
    )
    p.add_argument(
        "--run-queue",
        action="store_true",
        help="Start the DVC experiment queue after queueing.",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of queued jobs to run with dvc queue start -j.",
    )
    p.add_argument(
        "--name-prefix",
        default="eval-site",
        help="Experiment name prefix.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    args = p.parse_args()

    if args.sites:
        sites = normalize_sites(args.sites)
    else:
        sites = load_default_test_sites(args.params_yaml)

    if not sites:
        raise SystemExit("No sites found. Pass --sites or set exp.test_sites in params.yaml.")

    print(f"Sites to evaluate: {' '.join(sites)}", flush=True)

    for site in sites:
        exp_name = f"{args.name_prefix}-{sanitize_exp_name(site)}"

        cmd: List[str] = ["dvc", "exp", "run"]

        if args.queue:
            cmd.append("--queue")

        cmd.extend(
            [
                "--name",
                exp_name,
                "-S",
                f"exp.test_sites={site}",
                args.target,
            ]
        )

        run_cmd(cmd, dry_run=args.dry_run)

    if args.queue and args.run_queue:
        run_cmd(["dvc", "queue", "start", "-j", str(args.jobs)], dry_run=args.dry_run)


if __name__ == "__main__":
    main()
