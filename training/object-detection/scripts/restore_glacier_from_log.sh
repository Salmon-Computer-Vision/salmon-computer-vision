#!/usr/bin/env bash

set -uo pipefail

DEFAULT_WORKERS=32

usage() {
    cat <<EOF_USAGE
Usage:
  $0 request <log_file> [days] [tier] [workers]
  $0 status  <log_file> [workers]

Examples:
  # Submit restore requests with the defaults: 3 days, Bulk, 32 workers
  $0 request pack_tankeeah.log

  # Restore for 5 days using Standard retrieval and 64 concurrent workers
  $0 request pack_tankeeah.log 5 Standard 64

  # Check restore status using 32 workers
  $0 status pack_tankeeah.log

  # Check restore status using 64 workers
  $0 status pack_tankeeah.log 64

Restore tiers:
  Bulk
  Standard
  Expedited

Defaults:
  days    = 3
  tier    = Bulk
  workers = ${DEFAULT_WORKERS}

Notes:
  * request mode intentionally does NOT run head-object first. The source log
    already identifies objects that failed to download because they were
    archived, so skipping that check roughly halves the number of AWS API calls.
  * Restore requests are submitted concurrently. AWS currently supports up to
    1,000 Glacier restore requests/second per account; the default of 32 workers
    is intentionally conservative.
  * If a restore is already in progress, RestoreAlreadyInProgress is treated as
    a normal in-progress state rather than an error.
  * Re-running request on an object whose restore already completed can extend
    its temporary restore period. Use status when you only want to check progress.
EOF_USAGE
}

MODE="${1:-}"
LOG_FILE="${2:-}"

case "$MODE" in
    request)
        DAYS="${3:-3}"
        TIER="${4:-Bulk}"
        WORKERS="${5:-$DEFAULT_WORKERS}"
        ;;
    status)
        DAYS=""
        TIER=""
        WORKERS="${3:-$DEFAULT_WORKERS}"
        ;;
    *)
        usage
        exit 2
        ;;
esac

if [[ -z "$LOG_FILE" || ! -f "$LOG_FILE" ]]; then
    echo "ERROR: Log file not found: $LOG_FILE" >&2
    usage
    exit 2
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: aws CLI is not installed or not in PATH." >&2
    exit 2
fi

if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: workers must be a positive integer, got: $WORKERS" >&2
    exit 2
fi

if [[ "$MODE" == "request" ]]; then
    if ! [[ "$DAYS" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: days must be a positive integer, got: $DAYS" >&2
        exit 2
    fi

    case "$TIER" in
        Bulk|Standard|Expedited)
            ;;
        *)
            echo "ERROR: Invalid restore tier: $TIER" >&2
            echo "Valid values: Bulk, Standard, Expedited" >&2
            exit 2
            ;;
    esac
fi

# Give transient AWS/API failures a few chances without implementing our own
# retry/backoff loop. Explicit user settings still take precedence.
export AWS_RETRY_MODE="${AWS_RETRY_MODE:-standard}"
export AWS_MAX_ATTEMPTS="${AWS_MAX_ATTEMPTS:-5}"

# ---------------------------------------------------------------------------
# Extract unique S3 URLs from messages such as:
#
# warning: Skipping file s3://bucket/key.mp4. Object is of storage class ...
# ---------------------------------------------------------------------------

TMP_DIR="$(mktemp -d)"
URL_FILE="$TMP_DIR/urls.txt"
RESULT_DIR="$TMP_DIR/results"
mkdir -p "$RESULT_DIR"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

sed -n \
    's|.*Skipping file \(s3://[^ ]*\)\. Object is of storage class.*|\1|p' \
    "$LOG_FILE" \
    | sort -u \
    > "$URL_FILE"

TOTAL="$(wc -l < "$URL_FILE")"
TOTAL="${TOTAL//[[:space:]]/}"

if [[ "$TOTAL" -eq 0 ]]; then
    echo "No Glacier/Deep Archive object URLs found in:"
    echo "  $LOG_FILE"
    exit 0
fi

echo "Found $TOTAL unique archived object(s) in:"
echo "  $LOG_FILE"
echo "Mode:    $MODE"
echo "Workers: $WORKERS"
if [[ "$MODE" == "request" ]]; then
    echo "Days:    $DAYS"
    echo "Tier:    $TIER"
fi
echo

result_path() {
    local index="$1"
    printf '%s/%08d.result' "$RESULT_DIR" "$index"
}

write_result() {
    local index="$1"
    local status="$2"
    local url="$3"
    local detail="${4:-}"
    local path

    path="$(result_path "$index")"
    printf '%s\t%s\t%s\n' "$status" "$url" "$detail" > "$path"
}

# ---------------------------------------------------------------------------
# request worker
#
# Deliberately avoids head-object. In this workflow the URL only exists in the
# input list because an attempted download reported GLACIER/DEEP_ARCHIVE.
# ---------------------------------------------------------------------------

request_one() {
    local index="$1"
    local url="$2"
    local s3_path bucket key output rc

    s3_path="${url#s3://}"
    bucket="${s3_path%%/*}"
    key="${s3_path#*/}"

    output="$(aws s3api restore-object \
        --bucket "$bucket" \
        --key "$key" \
        --restore-request \
        "{\"Days\":${DAYS},\"GlacierJobParameters\":{\"Tier\":\"${TIER}\"}}" \
        --no-cli-pager \
        2>&1)"
    rc=$?

    if [[ "$rc" -eq 0 ]]; then
        write_result "$index" "REQUESTED" "$url"
        printf '[%d/%d] REQUESTED    %s\n' "$index" "$TOTAL" "$url"
        return 0
    fi

    if [[ "$output" == *"RestoreAlreadyInProgress"* ]]; then
        write_result "$index" "ONGOING" "$url" "RestoreAlreadyInProgress"
        printf '[%d/%d] IN PROGRESS  %s\n' "$index" "$TOTAL" "$url"
        return 0
    fi

    # Keep the complete AWS error in the per-object result file while only
    # printing its first line to the terminal.
    output="${output//$'\t'/ }"
    output="${output//$'\n'/ | }"
    write_result "$index" "FAILED" "$url" "$output"
    printf '[%d/%d] FAILED       %s\n' "$index" "$TOTAL" "$url" >&2
    return 0
}

# ---------------------------------------------------------------------------
# status worker
# ---------------------------------------------------------------------------

status_one() {
    local index="$1"
    local url="$2"
    local s3_path bucket key metadata rc storage_class restore

    s3_path="${url#s3://}"
    bucket="${s3_path%%/*}"
    key="${s3_path#*/}"

    metadata="$(aws s3api head-object \
        --bucket "$bucket" \
        --key "$key" \
        --query '[StorageClass, Restore]' \
        --output text \
        --no-cli-pager \
        2>/dev/null)"
    rc=$?

    if [[ "$rc" -ne 0 ]]; then
        write_result "$index" "FAILED" "$url" "head-object failed"
        printf '[%d/%d] ERROR        %s\n' "$index" "$TOTAL" "$url" >&2
        return 0
    fi

    storage_class="${metadata%%$'\t'*}"

    if [[ "$metadata" == *$'\t'* ]]; then
        restore="${metadata#*$'\t'}"
    else
        restore=""
    fi

    if [[ "$restore" == *'ongoing-request="false"'* ]]; then
        write_result "$index" "READY" "$url" "$restore"
        printf '[%d/%d] READY        %s\n' "$index" "$TOTAL" "$url"
        return 0
    fi

    if [[ "$restore" == *'ongoing-request="true"'* ]]; then
        write_result "$index" "ONGOING" "$url" "$restore"
        printf '[%d/%d] RESTORING    %s\n' "$index" "$TOTAL" "$url"
        return 0
    fi

    if [[ "$storage_class" != "GLACIER" &&
          "$storage_class" != "DEEP_ARCHIVE" ]]; then
        write_result "$index" "AVAILABLE" "$url" "$storage_class"
        printf '[%d/%d] AVAILABLE    %s\n' "$index" "$TOTAL" "$url"
        return 0
    fi

    write_result "$index" "NOT_REQUESTED" "$url" "$storage_class"
    printf '[%d/%d] NOT REQUESTED %s\n' "$index" "$TOTAL" "$url"
    return 0
}

# ---------------------------------------------------------------------------
# Bounded parallel runner using Bash's wait -n.
# ---------------------------------------------------------------------------

run_parallel() {
    local worker_fn="$1"
    local index=0
    local running=0
    local url

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue

        index=$((index + 1))
        "$worker_fn" "$index" "$url" &
        running=$((running + 1))

        if (( running >= WORKERS )); then
            wait -n || true
            running=$((running - 1))
        fi
    done < "$URL_FILE"

    wait || true
}

if [[ "$MODE" == "request" ]]; then
    run_parallel request_one
else
    run_parallel status_one
fi

# ---------------------------------------------------------------------------
# Aggregate worker results.
# ---------------------------------------------------------------------------

count_status() {
    local wanted="$1"
    awk -F '\t' -v wanted="$wanted" '$1 == wanted {count++} END {print count + 0}' \
        "$RESULT_DIR"/*.result
}

REQUESTED="$(count_status REQUESTED)"
READY="$(count_status READY)"
ONGOING="$(count_status ONGOING)"
NOT_REQUESTED="$(count_status NOT_REQUESTED)"
AVAILABLE="$(count_status AVAILABLE)"
FAILED="$(count_status FAILED)"
RESULT_COUNT="$(find "$RESULT_DIR" -maxdepth 1 -name '*.result' -type f | wc -l)"
RESULT_COUNT="${RESULT_COUNT//[[:space:]]/}"

echo
echo "============================================================"
echo "Summary"
echo "============================================================"
echo "Objects found:          $TOTAL"
echo "Worker results:         $RESULT_COUNT"

if [[ "$MODE" == "request" ]]; then
    echo "Restore submitted:      $REQUESTED"
    echo "Already in progress:    $ONGOING"
    echo "Errors:                 $FAILED"
else
    echo "Ready/restored:         $READY"
    echo "Restore in progress:    $ONGOING"
    echo "Not yet requested:      $NOT_REQUESTED"
    echo "Already available:      $AVAILABLE"
    echo "Errors:                 $FAILED"
fi

echo

if [[ "$RESULT_COUNT" -ne "$TOTAL" ]]; then
    echo "ERROR: Only $RESULT_COUNT of $TOTAL worker results were recorded." >&2
    exit 1
fi

if [[ "$MODE" == "status" ]]; then
    PENDING=$((ONGOING + NOT_REQUESTED + FAILED))

    if [[ "$PENDING" -eq 0 ]]; then
        echo "All objects are ready for download."
        exit 0
    fi

    echo "$PENDING object(s) are not ready yet."
    exit 1
fi

if [[ "$FAILED" -gt 0 ]]; then
    echo "$FAILED restore request(s) failed. Re-run request to retry them."
    exit 1
fi

echo "Restore requests submitted successfully."
echo "Use the following command to check progress:"
echo "  $0 status \"$LOG_FILE\" $WORKERS"
