#!/usr/bin/env bash
# Start the OSINT Kanban web UI (uvicorn) in the background.
#
# Usage:
#   ./start.sh [--reload] [--port N] [--host HOST]
#
# Writes PID to .uvicorn.pid and streams logs to uvicorn.log.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/.uvicorn.pid"
LOG_FILE="$ROOT/uvicorn.log"
HOST="127.0.0.1"
PORT="8000"
RELOAD_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reload)
      RELOAD_FLAG="--reload"
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift
      ;;
    --host)
      HOST="${2:?--host requires a value}"
      shift
      ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

# Bail if our own PID file shows a live process
if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "Already running (PID $EXISTING_PID). Use ./stop.sh first."
    exit 1
  fi
  rm -f "$PID_FILE"
fi

# Bail if the chosen port is already bound by something else
if lsof -iTCP:"$PORT" -sTCP:LISTEN -nP >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Check with:"
  echo "  lsof -iTCP:$PORT -sTCP:LISTEN -nP"
  exit 1
fi

if [[ ! -d "$ROOT/venv" ]]; then
  echo "No venv/ found in $ROOT."
  echo "Create one with:"
  echo "  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/venv/bin/activate"

echo "Starting uvicorn on $HOST:$PORT ${RELOAD_FLAG:+(with --reload)}..."
nohup env PYTHONPATH="$ROOT" python -m uvicorn web.app:app \
  --host "$HOST" --port "$PORT" --log-level info $RELOAD_FLAG \
  > "$LOG_FILE" 2>&1 &
UVICORN_PID=$!
echo "$UVICORN_PID" > "$PID_FILE"

# Give it a moment to bind, then verify it's alive
sleep 1
if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
  echo "Failed to start. Last lines of $LOG_FILE:"
  tail -n 20 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "Started."
echo "  PID:    $UVICORN_PID"
echo "  URL:    http://$HOST:$PORT/"
echo "  Log:    $LOG_FILE"
echo "  Follow: tail -f $LOG_FILE"
echo "  Stop:   ./stop.sh"
echo "  Status: ./status.sh"
