#!/usr/bin/env bash
set -e

DRIVE=/media/hdd
HC_URL=https://hc-ping.com/<destination_address>

if mountpoint "${DRIVE}" && touch "${DRIVE}/.testfile" && rm "${DRIVE}/.testfile"; then 
    curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}"
else 
    umount "${DRIVE}" && curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}/fail"
fi
