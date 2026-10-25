#!/usr/bin/env bash
#
# stop_pms.sh — stops all services started by start_pms.sh
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/logs/pms.pids"

echo "Stopping PMS services..."

# A missing PID file means nothing was tracked, not that nothing is running:
# a server started by hand never appears there. The port sweep below is what
# actually guarantees the ports are free, so it must run either way.
if [ -f "$PID_FILE" ]; then
  while read -r pid label; do
    [ -z "${pid:-}" ] && continue
    if kill "$pid" 2>/dev/null; then
      echo "  stopped pid $pid  $label"
    else
      echo "  (already gone) pid $pid  $label"
    fi
  done < "$PID_FILE"
else
  echo "  no PID file; falling back to the port sweep"
fi

# uvicorn --reload and vite spawn children, and anything restarted by hand is
# absent from the PID file entirely, so the ports are the real source of truth.
# Every port start_pms.sh launches must appear here — 3004 (the landing page)
# was missing, so apps/main survived every stop.
PORTS="8000 8001 8002 8003 3000 3001 3002 3003 3004"

for port in $PORTS; do
  lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill 2>/dev/null || true
done

# A uvicorn --reload parent that is mid-shutdown ignores SIGTERM and keeps the
# listening socket, which looks identical to a healthy server: the port accepts
# connections but nothing ever answers. Give the polite signal a moment, then
# force whatever is still holding a port.
sleep 2
for port in $PORTS; do
  stubborn="$(lsof -ti tcp:"$port" 2>/dev/null)"
  if [ -n "$stubborn" ]; then
    echo "  port $port did not release; forcing (pid $(echo "$stubborn" | tr '\n' ' '))"
    echo "$stubborn" | xargs -r kill -9 2>/dev/null || true
  fi
done

: > "$PID_FILE"

sleep 1
remaining="$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null \
  | awk -v ports="$PORTS" 'BEGIN{split(ports,p," ")} {for(i in p) if ($0 ~ ":"p[i]" ") {print; break}}')"
if [ -n "$remaining" ]; then
  echo "WARNING: still listening after stop:"
  echo "$remaining"
  exit 1
fi

echo "Done. All PMS ports free."
