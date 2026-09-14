#!/usr/bin/env bash

DRIVE="/media/hdd"
HC_URL="https://hc-ping.com/<destination_address>"

MAX_ATTEMPTS=5
RETRY_DELAY=5

check_drive() {
    local test_file="${DRIVE}/.drive_healthcheck_$$"

    if mountpoint -q "${DRIVE}" &&
       touch "${test_file}" &&
       rm "${test_file}"; then
        return 0
    fi

    # Best-effort cleanup in case touch succeeded but rm or another step failed.
    rm -f "${test_file}" 2>/dev/null || true

    return 1
}

for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
    if check_drive; then
        echo "Drive check passed on attempt ${attempt}/${MAX_ATTEMPTS}"
        curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}"
        exit 0
    fi

    echo "Drive check failed on attempt ${attempt}/${MAX_ATTEMPTS}"

    if [ "${attempt}" -lt "${MAX_ATTEMPTS}" ]; then
        sleep "${RETRY_DELAY}"
    fi
done

echo "Drive failed all ${MAX_ATTEMPTS} checks; unmounting and reporting failure."

# Avoid an unnecessary/erroring umount if it is already unmounted.
if mountpoint -q "${DRIVE}"; then
    umount "${DRIVE}" || true
fi

curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}/fail"
exit 1
