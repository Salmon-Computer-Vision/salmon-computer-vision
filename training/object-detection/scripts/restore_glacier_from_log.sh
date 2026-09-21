#!/usr/bin/env bash

set -uo pipefail

usage() {
    cat <<EOF
Usage:
  $0 request <log_file> [days] [tier]
  $0 status  <log_file>

Examples:
  $0 request pack_tankeeah.log
  $0 request pack_tankeeah.log 3 Bulk
  $0 request pack_tankeeah.log 5 Standard

  $0 status pack_tankeeah.log

Restore tiers:
  Bulk       Cheapest; Glacier Flexible Retrieval typically 5-12 hours
  Standard   Faster; typically 3-5 hours
  Expedited  Fastest; typically 1-5 minutes where supported

Defaults:
  days = 3
  tier = Bulk
EOF
}

MODE="${1:-}"
LOG_FILE="${2:-}"
DAYS="${3:-3}"
TIER="${4:-Bulk}"

if [[ "$MODE" != "request" && "$MODE" != "status" ]]; then
    usage
    exit 2
fi

if [[ -z "$LOG_FILE" || ! -f "$LOG_FILE" ]]; then
    echo "ERROR: Log file not found: $LOG_FILE" >&2
    usage
    exit 2
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: aws CLI is not installed or not in PATH." >&2
    exit 2
fi

case "$TIER" in
    Bulk|Standard|Expedited)
        ;;
    *)
        echo "ERROR: Invalid restore tier: $TIER" >&2
        exit 2
        ;;
esac


# ---------------------------------------------------------------------------
# Extract unique S3 URLs from messages like:
#
# warning: Skipping file s3://bucket/key.mp4. Object is of storage class ...
# ---------------------------------------------------------------------------

URL_FILE="$(mktemp)"
trap 'rm -f "$URL_FILE"' EXIT

sed -n \
    's|.*Skipping file \(s3://[^ ]*\)\. Object is of storage class.*|\1|p' \
    "$LOG_FILE" \
    | sort -u \
    > "$URL_FILE"

TOTAL="$(wc -l < "$URL_FILE")"
TOTAL="${TOTAL//[[:space:]]/}"

if [[ "$TOTAL" -eq 0 ]]; then
    echo "No Glacier object URLs found in:"
    echo "  $LOG_FILE"
    exit 0
fi

echo "Found $TOTAL unique Glacier object(s) in:"
echo "  $LOG_FILE"
echo


# ---------------------------------------------------------------------------
# Query storage class + restore state.
#
# Output is roughly:
#
# GLACIER    ongoing-request="true"
#
# or:
#
# GLACIER    ongoing-request="false", expiry-date="..."
# ---------------------------------------------------------------------------

get_restore_metadata() {
    local bucket="$1"
    local key="$2"

    aws s3api head-object \
        --bucket "$bucket" \
        --key "$key" \
        --query '[StorageClass, Restore]' \
        --output text \
        --no-cli-pager \
        2>/dev/null
}


READY=0
ONGOING=0
NOT_REQUESTED=0
FAILED=0
REQUESTED=0
NOT_ARCHIVED=0

INDEX=0

while IFS= read -r url; do
    [[ -z "$url" ]] && continue

    INDEX=$((INDEX + 1))

    # s3://bucket/path/to/object
    s3_path="${url#s3://}"
    bucket="${s3_path%%/*}"
    key="${s3_path#*/}"

    echo "[$INDEX/$TOTAL] $url"

    metadata="$(get_restore_metadata "$bucket" "$key")"
    rc=$?

    if [[ "$rc" -ne 0 ]]; then
        echo "  ERROR: Could not query object metadata."
        FAILED=$((FAILED + 1))
        echo
        continue
    fi

    # First field is StorageClass. Everything after the first tab is Restore.
    storage_class="${metadata%%$'\t'*}"

    if [[ "$metadata" == *$'\t'* ]]; then
        restore="${metadata#*$'\t'}"
    else
        restore=""
    fi

    # -----------------------------------------------------------------------
    # Already restored
    # -----------------------------------------------------------------------

    if [[ "$restore" == *'ongoing-request="false"'* ]]; then
        echo "  READY"
        echo "  Storage class: $storage_class"
        echo "  Restore: $restore"

        READY=$((READY + 1))
        echo
        continue
    fi

    # -----------------------------------------------------------------------
    # Restore currently running
    # -----------------------------------------------------------------------

    if [[ "$restore" == *'ongoing-request="true"'* ]]; then
        echo "  RESTORING"
        echo "  Storage class: $storage_class"

        ONGOING=$((ONGOING + 1))
        echo
        continue
    fi

    # -----------------------------------------------------------------------
    # Not an archive class requiring restore
    # -----------------------------------------------------------------------

    if [[ "$storage_class" != "GLACIER" &&
          "$storage_class" != "DEEP_ARCHIVE" ]]; then
        echo "  AVAILABLE (restore not required)"
        echo "  Storage class: $storage_class"

        NOT_ARCHIVED=$((NOT_ARCHIVED + 1))
        echo
        continue
    fi

    # -----------------------------------------------------------------------
    # Archived, but no restore has been requested
    # -----------------------------------------------------------------------

    if [[ "$MODE" == "status" ]]; then
        echo "  NOT REQUESTED"
        echo "  Storage class: $storage_class"

        NOT_REQUESTED=$((NOT_REQUESTED + 1))
        echo
        continue
    fi

    # -----------------------------------------------------------------------
    # Submit restore request
    # -----------------------------------------------------------------------

    echo "  REQUESTING RESTORE"
    echo "  Storage class: $storage_class"
    echo "  Tier: $TIER"
    echo "  Days: $DAYS"

    if aws s3api restore-object \
        --bucket "$bucket" \
        --key "$key" \
        --restore-request \
        "{\"Days\":${DAYS},\"GlacierJobParameters\":{\"Tier\":\"${TIER}\"}}" \
        --no-cli-pager
    then
        echo "  Restore request submitted."
        REQUESTED=$((REQUESTED + 1))
    else
        echo "  ERROR: Restore request failed."
        FAILED=$((FAILED + 1))
    fi

    echo

done < "$URL_FILE"


echo "============================================================"
echo "Summary"
echo "============================================================"
echo "Objects found:        $TOTAL"
echo "Ready/restored:       $READY"
echo "Restore in progress:  $ONGOING"

if [[ "$MODE" == "request" ]]; then
    echo "Restore requested:    $REQUESTED"
else
    echo "Not yet requested:    $NOT_REQUESTED"
fi

echo "Already available:    $NOT_ARCHIVED"
echo "Errors:               $FAILED"
echo


# Status mode returns success only when everything is available.
if [[ "$MODE" == "status" ]]; then
    PENDING=$((ONGOING + NOT_REQUESTED + FAILED))

    if [[ "$PENDING" -eq 0 ]]; then
        echo "All objects are ready for download."
        exit 0
    else
        echo "$PENDING object(s) are not ready yet."
        exit 1
    fi
fi

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
