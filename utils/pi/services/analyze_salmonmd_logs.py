#!/usr/bin/env python3
"""
Streaming analysis of salmonmd logs for restarts/outages.

Features:
- Reads logs line-by-line (streaming, low memory).
- Extracts ORG/site/device from path: /media/hdd/ORG/site/device/logs/...
- Detects "restart" markers (default: lines containing 'Writing logs to').
- For each pair of consecutive restarts, estimates:
    * uptime_seconds   = last_non_restart_log_prev_run - prev_restart_time
    * downtime_seconds = current_restart_time - last_non_restart_log_prev_run
- Appends outage rows to a CSV (header only once).
- Uses a JSON state file to remember:
    * which log files have been fully processed
    * the last incident number used
- In directory mode, skips today's log file(s) based on date encoded in filename,
  so we don't prematurely mark an actively written logfile as "done".

Typical usage in directory mode:

  python3 analyze_salmonmd_logs.py \
    --log-dir /media/hdd/ORG/site/device/logs/salmonmd_logs \
    --pattern 'salmonmd_logs_*' \
    --output-csv /media/hdd/ORG/site/device/salmonmd_outages.csv \
    --min-downtime-seconds 5
    --org ORG
    --site site
    --device device-0

If you change logic and want to recompute everything, delete:
  - the CSV
  - the state file (default: <output_csv>.state.json)
and re-run.
"""

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class StreamState:
    prev_restart_ts: Optional[datetime] = None
    prev_restart_file: Optional[str] = None
    prev_last_non_restart_ts: Optional[datetime] = None
    incident_counter: int = 0


# ---------------------------------------------------------------------------
# Helpers for path + dates
# ---------------------------------------------------------------------------

HEALTH_KEYWORDS = [
    "Retrieval time",
    "BGSub:",
    "Size of shared frames",
    "Time elapsed:",
    "Cont save:",
    "Writing continuous video to",
]


def is_healthy_message(message: str) -> bool:
    """Return True if this log line indicates the system is actually processing frames."""
    for kw in HEALTH_KEYWORDS:
        if kw in message:
            return True
    return False

def parse_org_site_device(path: Path) -> Tuple[str, str, str]:
    """
    Extract ORG, site, device from /media/hdd/ORG/site/device/logs/...

    Returns ("UNKNOWN_ORG", "UNKNOWN_SITE", "UNKNOWN_DEVICE") if pattern
    doesn't match.
    """
    parts = path.parts
    org = "UNKNOWN_ORG"
    site = "UNKNOWN_SITE"
    device = "UNKNOWN_DEVICE"
    try:
        # ... /media/hdd/ORG/site/device/logs/...
        i = parts.index("media")
        if parts[i + 1] == "hdd":
            org = parts[i + 2]
            site = parts[i + 3]
            device = parts[i + 4]
    except Exception:
        pass
    return org, site, device


DATE_RE = re.compile(r"(\d{8})")  # e.g. salmonmd_logs_20250625.txt


def log_date_from_name(path: Path) -> Optional[date]:
    """
    Extract a date from filename based on an 8-digit YYYYMMDD substring.

    Example:
      salmonmd_logs_20250625.txt -> date(2025, 6, 25)

    Returns None if no date-like pattern is found.
    """
    m = DATE_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> Optional[tuple]:
    """
    Parse lines like:
      2025-06-25 05:21:24,544 - INFO [run_motion_detect_rtsp.py:61] - message

    Returns (ts: datetime, level: str, module: str, message: str)
    or None if unparsable.
    """
    line = line.rstrip("\n")
    if not line:
        return None

    parts = line.split(" - ", 2)
    if len(parts) < 3:
        return None

    ts_raw, level_module_raw, message = parts
    try:
        ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None

    level_raw, module_raw = level_module_raw.split()
    module = module_raw.strip()
    if module.startswith("[") and module.endswith("]"):
        module = module[1:-1]
    return ts, level_raw.strip(), module, message.strip()


# ---------------------------------------------------------------------------
# Core streaming logic
# ---------------------------------------------------------------------------

def process_line(
    ts: datetime,
    message: str,
    filename: str,
    org: str,
    site: str,
    device: str,
    state: StreamState,
    writer: csv.writer,
    restart_keyword: str,
    min_downtime_seconds: float,
) -> None:
    """
    Update streaming state for one parsed log line.
    If we detect a new restart and have enough info about the previous run,
    write an outage row to CSV.
    """
    is_restart = restart_keyword in message

    if is_restart:
        curr_restart = ts

        # We can compute an outage if:
        # - we have a previous restart time (start of previous run)
        # - and at least one non-restart log after that (the last log in that run)
        if state.prev_restart_ts and state.prev_last_non_restart_ts:
            uptime = (state.prev_last_non_restart_ts - state.prev_restart_ts).total_seconds()
            downtime = (curr_restart - state.prev_last_non_restart_ts).total_seconds()

            if downtime >= min_downtime_seconds:
                state.incident_counter += 1
                writer.writerow(
                    [
                        state.incident_counter,
                        org,
                        site,
                        device,
                        state.prev_restart_ts.isoformat(sep=" "),
                        state.prev_restart_file,
                        state.prev_last_non_restart_ts.isoformat(sep=" "),
                        curr_restart.isoformat(sep=" "),
                        filename,
                        f"{uptime:.3f}",
                        f"{downtime:.3f}",
                        "", # TODO: Populate with error message
                    ]
                )

        # Begin new run
        state.prev_restart_ts = curr_restart
        state.prev_restart_file = filename
        state.prev_last_non_restart_ts = None

    else:
        # Only treat certain messages as "healthy work"
        if is_healthy_message(message):
            state.prev_last_non_restart_ts = ts


def process_file(
    file_path: Path,
    state: StreamState,
    writer: csv.writer,
    restart_keyword: str,
    min_downtime_seconds: float,
    org: str,
    site: str,
    device: str,
) -> None:
    """
    Stream a single logfile line-by-line and update state / CSV.
    """
    if org in "UNKNOWN_ORG":
        org, site, device = parse_org_site_device(file_path)

    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parsed = parse_log_line(line)
            if not parsed:
                continue
            ts, _, _, message = parsed
            process_line(
                ts=ts,
                message=message,
                filename=str(file_path),
                org=org,
                site=site,
                device=device,
                state=state,
                writer=writer,
                restart_keyword=restart_keyword,
                min_downtime_seconds=min_downtime_seconds,
            )


# ---------------------------------------------------------------------------
# Persistent state management
# ---------------------------------------------------------------------------

def load_processor_state(state_file: Path) -> Dict[str, Any]:
    """
    Load JSON state with structure:
      {
        "processed_files": [...],
        "last_incident": <int>
      }
    """
    if not state_file.exists():
        return {"processed_files": [], "last_incident": 0}
    try:
        return json.loads(state_file.read_text())
    except Exception:
        # If corrupted, start fresh
        return {"processed_files": [], "last_incident": 0}


def save_processor_state(state_file: Path, data: Dict[str, Any]) -> None:
    """
    Safely write state JSON (write temp file then replace).
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(state_file.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(state_file)


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Streaming analysis of salmonmd logs for restarts/outages with persistent state. \
                Expects /media/hdd/ORG/site/device/log path otherwise please specify ORG, site, and device names"
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--log-file", type=Path, help="Analyze a single logfile.")
    src.add_argument("--log-dir", type=Path, help="Analyze a directory of logfiles (recommended).")

    parser.add_argument(
        "--pattern",
        default="*",
        help="Glob pattern when using --log-dir (default: '*').",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        required=True,
        help="CSV file to append outage rows to.",
    )
    parser.add_argument(
        "--restart-keyword",
        default="Writing logs to",
        help="Substring that identifies a restart line (default: 'Writing logs to').",
    )
    parser.add_argument(
        "--min-downtime-seconds",
        type=float,
        default=0.0,
        help="Only record outages with downtime >= this many seconds.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        help="JSON file tracking processed logfiles; default: <output_csv>.state.json",
    )
    parser.add_argument(
        "--org",
        default="UNKNOWN_ORG",
        help="Set the ORG string if cannot be inferred from path",
    )
    parser.add_argument(
        "--site",
        default="unknown_site",
        help="Set the site string if cannot be inferred from path",
    )
    parser.add_argument(
        "--device",
        default="unknown_device",
        help="Set the device string if cannot be inferred from path",
    )

    args = parser.parse_args()

    # Determine state file path
    if args.state_file is not None:
        state_path = args.state_file
    else:
        state_path = args.output_csv.with_suffix(args.output_csv.suffix + ".state.json")

    # Load (or initialize) state
    processor_state = load_processor_state(state_path)
    processed_files = set(processor_state.get("processed_files", []))
    last_incident = int(processor_state.get("last_incident", 0))

    # Initialize streaming state
    state = StreamState(incident_counter=last_incident)

    # CSV header handling
    output_exists = args.output_csv.exists()
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)

    today = date.today()

    with args.output_csv.open("a", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)

        # Header only once
        if not output_exists:
            writer.writerow(
                [
                    "incident",
                    "org",
                    "site",
                    "device",
                    "prev_restart_time",
                    "prev_restart_file",
                    "prev_last_log_time",
                    "curr_restart_time",
                    "curr_restart_file",
                    "uptime_seconds",
                    "downtime_seconds",
                    "error_msg",
                ]
            )

        # Single-file mode: process exactly this file, regardless of date,
        # and mark it processed (so you don't double-count if you call via log-dir later).
        if args.log_file:
            fp = args.log_file.resolve()
            if str(fp) not in processed_files:
                process_file(
                    file_path=fp,
                    state=state,
                    writer=writer,
                    restart_keyword=args.restart_keyword,
                    min_downtime_seconds=args.min_downtime_seconds,
                    org=args.org,
                    site=args.site,
                    device=args.device,
                )
                processed_files.add(str(fp))
        else:
            # Directory mode: process only files not yet processed AND whose date
            # (from filename) is strictly before today. That way we never mark
            # an actively written "today" logfile as done.
            for fp in sorted(args.log_dir.glob(args.pattern)):
                fp_abs = fp.resolve()
                if str(fp_abs) in processed_files:
                    continue

                log_day = log_date_from_name(fp_abs)
                if log_day is not None and log_day >= today:
                    # Skip today's (or weird future-dated) logfile
                    continue

                process_file(
                    file_path=fp_abs,
                    state=state,
                    writer=writer,
                    restart_keyword=args.restart_keyword,
                    min_downtime_seconds=args.min_downtime_seconds,
                    org=args.org,
                    site=args.site,
                    device=args.device,
                )
                processed_files.add(str(fp_abs))

    # Save updated processor state (even if no outages occurred)
    processor_state["processed_files"] = sorted(processed_files)
    processor_state["last_incident"] = state.incident_counter
    save_processor_state(state_path, processor_state)

    print(f"Done. Last incident number: {state.incident_counter}")
    print(f"Processed files tracked in: {state_path}")


if __name__ == "__main__":
    main()

