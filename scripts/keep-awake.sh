#!/bin/sh
# Ping the Render health URL so a free instance does not sleep.
# Render spins down after 15 minutes without inbound traffic, so 10 minutes
# is enough. This only runs while this computer stays awake.
# Usage: scripts/keep-awake.sh
#        KEEP_AWAKE_INTERVAL=60 scripts/keep-awake.sh

url="${KEEP_AWAKE_URL:-https://line-scheduler-ybzo.onrender.com/health}"
interval="${KEEP_AWAKE_INTERVAL:-600}"

echo "Pinging $url every ${interval}s. Ctrl-C to stop."
while true; do
  printf '%s ' "$(date '+%H:%M:%S')"
  curl -fsS -m 90 -w "code:%{http_code} time:%{time_total}s\n" "$url" \
    || echo "ping failed"
  sleep "$interval"
done
