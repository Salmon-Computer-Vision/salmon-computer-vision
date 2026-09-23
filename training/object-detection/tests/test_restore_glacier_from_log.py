
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "restore_glacier_from_log.sh"
)


FAKE_AWS = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def arg_value(args, flag, default=None):
    try:
        return args[args.index(flag) + 1]
    except (ValueError, IndexError):
        return default


args = sys.argv[1:]
scenario_path = Path(os.environ["FAKE_AWS_SCENARIO_FILE"])
call_log_path = Path(os.environ["FAKE_AWS_CALL_LOG"])

scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

operation = " ".join(args[:2])
bucket = arg_value(args, "--bucket", "")
key = arg_value(args, "--key", "")
restore_request = arg_value(args, "--restore-request")

record = {
    "operation": operation,
    "bucket": bucket,
    "key": key,
    "restore_request": restore_request,
    "aws_retry_mode": os.environ.get("AWS_RETRY_MODE"),
    "aws_max_attempts": os.environ.get("AWS_MAX_ATTEMPTS"),
}

# Each fake AWS process appends exactly one short JSON line.
# The Bash script may invoke us concurrently, so tests never depend on order.
with call_log_path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, sort_keys=True) + "\n")

entry = scenario.get(key, {})

if operation == "s3api restore-object":
    state = entry.get("request", "requested")

    if state == "requested":
        sys.exit(0)

    if state == "ongoing":
        print(
            "An error occurred (RestoreAlreadyInProgress) when calling "
            "the RestoreObject operation: Object restore is already in progress",
            file=sys.stderr,
        )
        sys.exit(255)

    if state == "failed":
        print(
            "An error occurred (AccessDenied) when calling "
            "the RestoreObject operation: Access Denied",
            file=sys.stderr,
        )
        sys.exit(255)

    print(f"Unknown fake request state: {state}", file=sys.stderr)
    sys.exit(99)

if operation == "s3api head-object":
    state = entry.get("status", "ready")
    storage_class = entry.get("storage_class", "GLACIER")

    if state == "failed":
        print("fake head-object failure", file=sys.stderr)
        sys.exit(255)

    if state == "ready":
        print(
            storage_class
            + '\tongoing-request="false", '
              'expiry-date="Fri, 25 Sep 2026 00:00:00 GMT"'
        )
        sys.exit(0)

    if state == "ongoing":
        print(storage_class + '\tongoing-request="true"')
        sys.exit(0)

    if state == "available":
        print(storage_class + "\tNone")
        sys.exit(0)

    if state == "not_requested":
        print(storage_class + "\tNone")
        sys.exit(0)

    print(f"Unknown fake status state: {state}", file=sys.stderr)
    sys.exit(99)

print(f"Unexpected fake aws invocation: {args!r}", file=sys.stderr)
sys.exit(98)
"""


def glacier_line(bucket: str, key: str, storage_class: str = "GLACIER") -> str:
    return (
        f"warning: Skipping file s3://{bucket}/{key}. "
        f"Object is of storage class {storage_class}. "
        "Unable to perform download operations on archived objects.\n"
    )


@pytest.fixture
def fake_aws_env(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    aws_path = bin_dir / "aws"
    aws_path.write_text(FAKE_AWS, encoding="utf-8")
    aws_path.chmod(0o755)

    scenario_path = tmp_path / "scenario.json"
    call_log = tmp_path / "aws_calls.jsonl"

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["FAKE_AWS_SCENARIO_FILE"] = str(scenario_path)
    env["FAKE_AWS_CALL_LOG"] = str(call_log)

    # Let the Bash script establish its documented defaults.
    env.pop("AWS_RETRY_MODE", None)
    env.pop("AWS_MAX_ATTEMPTS", None)

    def run(
        mode: str,
        log_text: str,
        *,
        scenario: dict | None = None,
        extra_args: tuple[str, ...] = (),
        env_overrides: dict[str, str] | None = None,
    ):
        log_path = tmp_path / "pack.log"
        log_path.write_text(log_text, encoding="utf-8")

        scenario_path.write_text(
            json.dumps(scenario or {}, indent=2),
            encoding="utf-8",
        )
        call_log.write_text("", encoding="utf-8")

        run_env = env.copy()
        if env_overrides:
            run_env.update(env_overrides)

        cp = subprocess.run(
            ["/bin/bash", str(SCRIPT), mode, str(log_path), *extra_args],
            text=True,
            capture_output=True,
            env=run_env,
            check=False,
        )

        calls = []
        if call_log.exists():
            for line in call_log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    calls.append(json.loads(line))

        return cp, calls

    return run


def test_request_defaults_deduplicates_urls_and_calls_restore_only(fake_aws_env):
    log = (
        "some unrelated output\n"
        + glacier_line("bucket-a", "ORG/site/device/a.mp4")
        + glacier_line("bucket-a", "ORG/site/device/a.mp4")
        + glacier_line("bucket-b", "ORG/site/device/b.mp4", "DEEP_ARCHIVE")
    )

    scenario = {
        "ORG/site/device/a.mp4": {"request": "requested"},
        "ORG/site/device/b.mp4": {"request": "requested"},
    }

    cp, calls = fake_aws_env("request", log, scenario=scenario)

    assert cp.returncode == 0, cp.stderr
    assert "Found 2 unique archived object(s)" in cp.stdout
    assert "Mode:    request" in cp.stdout
    assert "Workers: 32" in cp.stdout
    assert "Days:    3" in cp.stdout
    assert "Tier:    Bulk" in cp.stdout
    assert "Restore submitted:      2" in cp.stdout
    assert "Already in progress:    0" in cp.stdout
    assert "Errors:                 0" in cp.stdout
    assert "Restore requests submitted successfully." in cp.stdout

    assert len(calls) == 2
    assert {c["operation"] for c in calls} == {"s3api restore-object"}
    assert {(c["bucket"], c["key"]) for c in calls} == {
        ("bucket-a", "ORG/site/device/a.mp4"),
        ("bucket-b", "ORG/site/device/b.mp4"),
    }

    for call in calls:
        request = json.loads(call["restore_request"])
        assert request == {
            "Days": 3,
            "GlacierJobParameters": {"Tier": "Bulk"},
        }
        assert call["aws_retry_mode"] == "standard"
        assert call["aws_max_attempts"] == "5"


def test_request_custom_days_tier_workers(fake_aws_env):
    key = "ORG/site/device/a.mp4"
    cp, calls = fake_aws_env(
        "request",
        glacier_line("bucket", key),
        scenario={key: {"request": "requested"}},
        extra_args=("7", "Standard", "4"),
    )

    assert cp.returncode == 0
    assert "Workers: 4" in cp.stdout
    assert "Days:    7" in cp.stdout
    assert "Tier:    Standard" in cp.stdout

    assert len(calls) == 1
    request = json.loads(calls[0]["restore_request"])
    assert request["Days"] == 7
    assert request["GlacierJobParameters"]["Tier"] == "Standard"


def test_request_restore_already_in_progress_is_not_an_error(fake_aws_env):
    key = "ORG/site/device/a.mp4"
    cp, calls = fake_aws_env(
        "request",
        glacier_line("bucket", key),
        scenario={key: {"request": "ongoing"}},
    )

    assert cp.returncode == 0
    assert len(calls) == 1
    assert "Already in progress:    1" in cp.stdout
    assert "Errors:                 0" in cp.stdout
    assert "Restore requests submitted successfully." in cp.stdout


def test_request_generic_aws_failure_returns_one(fake_aws_env):
    key = "ORG/site/device/a.mp4"
    cp, calls = fake_aws_env(
        "request",
        glacier_line("bucket", key),
        scenario={key: {"request": "failed"}},
    )

    assert cp.returncode == 1
    assert len(calls) == 1
    assert "Restore submitted:      0" in cp.stdout
    assert "Errors:                 1" in cp.stdout
    assert "1 restore request(s) failed." in cp.stdout
    assert "FAILED" in cp.stderr


def test_status_all_ready_or_available_returns_zero(fake_aws_env):
    ready = "ORG/site/device/ready.mp4"
    available = "ORG/site/device/available.mp4"

    log = (
        glacier_line("bucket", ready)
        + glacier_line("bucket", available)
    )
    scenario = {
        ready: {
            "status": "ready",
            "storage_class": "GLACIER",
        },
        available: {
            "status": "available",
            "storage_class": "STANDARD",
        },
    }

    cp, calls = fake_aws_env(
        "status",
        log,
        scenario=scenario,
        extra_args=("2",),
    )

    assert cp.returncode == 0, cp.stderr
    assert "Mode:    status" in cp.stdout
    assert "Workers: 2" in cp.stdout
    assert "Ready/restored:         1" in cp.stdout
    assert "Already available:      1" in cp.stdout
    assert "Restore in progress:    0" in cp.stdout
    assert "Not yet requested:      0" in cp.stdout
    assert "Errors:                 0" in cp.stdout
    assert "All objects are ready for download." in cp.stdout

    assert len(calls) == 2
    assert {c["operation"] for c in calls} == {"s3api head-object"}


def test_status_ongoing_and_not_requested_returns_one(fake_aws_env):
    ongoing = "ORG/site/device/ongoing.mp4"
    not_requested = "ORG/site/device/not-requested.mp4"

    log = (
        glacier_line("bucket", ongoing)
        + glacier_line("bucket", not_requested, "DEEP_ARCHIVE")
    )
    scenario = {
        ongoing: {
            "status": "ongoing",
            "storage_class": "GLACIER",
        },
        not_requested: {
            "status": "not_requested",
            "storage_class": "DEEP_ARCHIVE",
        },
    }

    cp, calls = fake_aws_env("status", log, scenario=scenario)

    assert cp.returncode == 1
    assert len(calls) == 2
    assert "Restore in progress:    1" in cp.stdout
    assert "Not yet requested:      1" in cp.stdout
    assert "2 object(s) are not ready yet." in cp.stdout


def test_status_head_object_failure_counts_as_error(fake_aws_env):
    key = "ORG/site/device/fail.mp4"
    cp, calls = fake_aws_env(
        "status",
        glacier_line("bucket", key),
        scenario={key: {"status": "failed"}},
    )

    assert cp.returncode == 1
    assert len(calls) == 1
    assert "Errors:                 1" in cp.stdout
    assert "1 object(s) are not ready yet." in cp.stdout
    assert "ERROR" in cp.stderr


def test_status_glacier_without_restore_is_not_requested(fake_aws_env):
    key = "ORG/site/device/a.mp4"
    cp, _ = fake_aws_env(
        "status",
        glacier_line("bucket", key),
        scenario={
            key: {
                "status": "not_requested",
                "storage_class": "GLACIER",
            }
        },
    )

    assert cp.returncode == 1
    assert "Not yet requested:      1" in cp.stdout


def test_no_matching_archived_urls_exits_without_aws_calls(fake_aws_env):
    cp, calls = fake_aws_env(
        "request",
        "normal log line\nanother line\n",
    )

    assert cp.returncode == 0
    assert calls == []
    assert "No Glacier/Deep Archive object URLs found in:" in cp.stdout


def test_request_preserves_explicit_aws_retry_environment(fake_aws_env):
    key = "ORG/site/device/a.mp4"

    cp, calls = fake_aws_env(
        "request",
        glacier_line("bucket", key),
        scenario={key: {"request": "requested"}},
        env_overrides={
            "AWS_RETRY_MODE": "adaptive",
            "AWS_MAX_ATTEMPTS": "9",
        },
    )

    assert cp.returncode == 0
    assert calls[0]["aws_retry_mode"] == "adaptive"
    assert calls[0]["aws_max_attempts"] == "9"


@pytest.mark.parametrize(
    ("mode", "extra_args", "expected"),
    [
        ("request", ("0", "Bulk", "1"), "days must be a positive integer"),
        ("request", ("abc", "Bulk", "1"), "days must be a positive integer"),
        ("request", ("3", "Fast", "1"), "Invalid restore tier"),
        ("request", ("3", "Bulk", "0"), "workers must be a positive integer"),
        ("request", ("3", "Bulk", "abc"), "workers must be a positive integer"),
        ("status", ("0",), "workers must be a positive integer"),
        ("status", ("abc",), "workers must be a positive integer"),
    ],
)
def test_argument_validation(
    fake_aws_env,
    mode,
    extra_args,
    expected,
):
    cp, calls = fake_aws_env(
        mode,
        glacier_line("bucket", "ORG/site/device/a.mp4"),
        extra_args=extra_args,
    )

    assert cp.returncode == 2
    assert expected in cp.stderr
    assert calls == []


def test_invalid_mode_prints_usage_and_returns_two(tmp_path: Path):
    cp = subprocess.run(
        ["/bin/bash", str(SCRIPT), "bogus"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert cp.returncode == 2
    assert "Usage:" in cp.stdout


def test_missing_log_file_returns_two(fake_aws_env, tmp_path: Path):
    # Use the fake AWS PATH so this test is specifically about the missing log.
    log = tmp_path / "does-not-exist.log"

    # Obtain the fixture's environment indirectly by creating a valid run first
    # is unnecessary; construct a tiny fake aws path locally instead.
    bin_dir = tmp_path / "missing-log-bin"
    bin_dir.mkdir()
    aws = bin_dir / "aws"
    aws.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    aws.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    cp = subprocess.run(
        ["/bin/bash", str(SCRIPT), "status", str(log)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert cp.returncode == 2
    assert "ERROR: Log file not found:" in cp.stderr
    assert "Usage:" in cp.stdout


def test_missing_aws_cli_returns_two(tmp_path: Path):
    log = tmp_path / "pack.log"
    log.write_text(
        glacier_line("bucket", "ORG/site/device/a.mp4"),
        encoding="utf-8",
    )

    # Script reaches command -v aws before any external utility needed for
    # actual processing, so an empty PATH isolates this branch.
    env = os.environ.copy()
    env["PATH"] = ""

    cp = subprocess.run(
        ["/bin/bash", str(SCRIPT), "status", str(log)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert cp.returncode == 2
    assert "aws CLI is not installed or not in PATH" in cp.stderr


def test_request_and_status_parse_bucket_and_full_key(fake_aws_env):
    key = "HIRMD/tankeeah/jetson-0/motion_vids/video.name-with_parts.mp4"
    log = glacier_line("prod-salmonvision-edge-assets-labelstudio-source", key)

    cp, calls = fake_aws_env(
        "request",
        log,
        scenario={key: {"request": "requested"}},
    )

    assert cp.returncode == 0
    assert calls == [
        {
            "operation": "s3api restore-object",
            "bucket": "prod-salmonvision-edge-assets-labelstudio-source",
            "key": key,
            "restore_request": json.dumps(
                {
                    "Days": 3,
                    "GlacierJobParameters": {"Tier": "Bulk"},
                },
                separators=(",", ":"),
            ),
            "aws_retry_mode": "standard",
            "aws_max_attempts": "5",
        }
    ]


def test_mixed_request_results_are_aggregated_correctly(fake_aws_env):
    requested = "ORG/site/device/requested.mp4"
    ongoing = "ORG/site/device/ongoing.mp4"
    failed = "ORG/site/device/failed.mp4"

    log = (
        glacier_line("bucket", requested)
        + glacier_line("bucket", ongoing)
        + glacier_line("bucket", failed)
    )
    scenario = {
        requested: {"request": "requested"},
        ongoing: {"request": "ongoing"},
        failed: {"request": "failed"},
    }

    cp, calls = fake_aws_env(
        "request",
        log,
        scenario=scenario,
        extra_args=("3", "Bulk", "3"),
    )

    assert cp.returncode == 1
    assert len(calls) == 3
    assert "Worker results:         3" in cp.stdout
    assert "Restore submitted:      1" in cp.stdout
    assert "Already in progress:    1" in cp.stdout
    assert "Errors:                 1" in cp.stdout
