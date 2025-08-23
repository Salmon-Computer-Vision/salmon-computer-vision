#!/usr/bin/env bash
set -euo pipefail

MNT="${SMB_MNT:-/app/drive/hdd}"
FALLBACK="/app/drive/local_hdd"
SHARE="${SMB_SHARE:?//server/share is required}"
OPTS="${SMB_OPTS:-rw,vers=3.0,soft,timeo=5,retrans=3,uid=1000,gid=1000,file_mode=0664,dir_mode=0775}"

mkdir -p "$MNT" "$FALLBACK"

attempt_mount() {
  if command -v mount.cifs >/dev/null 2>&1; then
    # credentials are optional; only add if file exists
    if [[ -f "$CRED_FILE" ]]; then
      mount -t cifs "$SHARE" "$MNT" -o "credentials=$CRED_FILE,${OPTS}" && return 0
    else
      mount -t cifs "$SHARE" "$MNT" -o "${OPTS}" && return 0
    fi
  fi
  return 1
}

# Initial mount retries (don’t block forever)
for i in {1..10}; do
  if attempt_mount; then
    echo "[entrypoint] CIFS mounted at $MNT"
    break
  fi
  echo "[entrypoint] CIFS mount failed ($i/10). Retrying in 6s…"
  sleep 6
done

# If still not mounted, symlink the working path to fallback
if ! mountpoint -q "$MNT"; then
  echo "[entrypoint] Using fallback at $FALLBACK (share offline)."
fi

# Background watchdog: if mount drops, try to remount
(
  while true; do
    if ! mountpoint -q "$MNT"; then
      echo "[watchdog] Share offline. Attempting remount…"
      attempt_mount || true
    fi
    sleep 10
  done
) &

# Optional: quick write test; if *both* mount and fallback aren’t writable, exit to trigger restart
if ! sh -c "touch ${MNT}/.rw_test.$$ 2>/dev/null && rm -f ${MNT}/.rw_test.$$" \
   && ! sh -c "touch ${FALLBACK}/.rw_test.$$ 2>/dev/null && rm -f ${FALLBACK}/.rw_test.$$"; then
  echo "[entrypoint] Neither mount nor fallback writable. Exiting."
  exit 1
fi

# Run your app (it can prioritize $MNT when mounted; else use $FALLBACK)
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libstdc++.so.6
exec python3 watcher.py --weights "${WEIGHTS}" ${FLAGS:-}

