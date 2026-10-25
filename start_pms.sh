#!/usr/bin/env bash
#
# start_pms.sh — macOS/Linux launcher for the Project Management System.
# Starts all 4 backends (own venvs) + 4 frontends in the background.
# Logs go to logs/<service>.log. PIDs are tracked in logs/pms.pids.
# Stop everything with ./stop_pms.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/logs"
PID_FILE="$LOG_DIR/pms.pids"
mkdir -p "$LOG_DIR"
: > "$PID_FILE"

echo "========================================================"
echo " Starting Project Management System (8 services)"
echo "========================================================"

start_backend() {
  local name="$1" port="$2"
  local dir="$ROOT/backend/$name"
  if [ ! -x "$dir/venv/bin/uvicorn" ]; then
    echo "  !! $name: venv not found. Run its setup first." >&2
    return
  fi
  ( cd "$dir" && venv/bin/uvicorn app.main:app --reload --port "$port" \
      > "$LOG_DIR/$name.log" 2>&1 ) &
  echo "$! $name (backend :$port)" >> "$PID_FILE"
  echo "  -> $name backend  :$port  (pid $!)"
}

start_frontend() {
  local name="$1" port="$2"
  local dir="$ROOT/apps/$name"
  ( cd "$dir" && npm run dev > "$LOG_DIR/$name-frontend.log" 2>&1 ) &
  echo "$! $name (frontend :$port)" >> "$PID_FILE"
  echo "  -> $name frontend :$port  (pid $!)"
}

echo "Backends:"
start_backend admin-api   8000
start_backend panel-api   8001
start_backend student-api 8002
start_backend mentor-api  8003

echo "Frontends:"
start_frontend admin   3000
start_frontend panel   3001
start_frontend student 3002
start_frontend mentor  3003
start_frontend main    3004

echo
echo "All services launched. URLs:"
echo "  Admin   http://localhost:3000  (api :8000)"
echo "  Panel   http://localhost:3001  (api :8001)"
echo "  Student http://localhost:3002  (api :8002)"
echo "  Mentor  http://localhost:3003  (api :8003)"
echo "  Landing http://localhost:3004"
echo
echo "Logs:  tail -f logs/<service>.log"
echo "Stop:  ./stop_pms.sh"
