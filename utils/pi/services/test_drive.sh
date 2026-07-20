#!/usr/bin/env bash
set -e

HC_URL=https://hc-ping.com/<destination_address>

if mountpoint /media/hdd && touch /media/hdd/.testfile && rm /media/hdd/.testfile; then 
    curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}"
else 
    umount /media/hdd && curl -fsS -m 10 --retry 5 -o /dev/null "${HC_URL}/fail"
fi
