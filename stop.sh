#!/usr/bin/env bash
# Stop the OSINT uvicorn server started via ./start.sh.
# Sends SIGTERM, waits up to 5s, then escalates to SIGKILL if needed.
# If no PID file exists, falls back to pkill on the uvicorn web.app pattern.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.uvicorn.pid"

_UVICORN_RE='^[^ ]+[Pp]ython[^ ]* -m uvicorn web\.app:app'

if [[ ! -f "$PID_FILE" ]]; then
  if pgrep -f "$_UVICORN_RE" >/dev/null; then
    echo "No PID file, but uvicorn is running. Sending SIGTERM..."
    pkill -TERM -f "$_UVICORN_RE" || true
    sleep 2
    if pgrep -f "$_UVICORN_RE" >/dev/null; then
      echo "Still alive. Sending SIGKILL..."
      pkill -KILL -f "$_UVICORN_RE" || true
    fi
    echo "Done."
  else
    echo "Not running (no PID file, no matching process)."
  fi
  exit 0
fi

PID="$(cat "$PID_FILE")"

if ! kill -0 "$PID" 2>/dev/null; then
  echo "Process $PID not running (stale PID file). Removing."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Sending SIGTERM to $PID..."
kill -TERM "$PID" || true

for _ in 1 2 3 4 5; do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Stopped cleanly."
    exit 0
  fi
  sleep 1
done

echo "Process still alive after 5s. Escalating to SIGKILL..."
kill -KILL "$PID" 2>/dev/null || true
sleep 1

if kill -0 "$PID" 2>/dev/null; then
  echo "ERROR: could not kill $PID" >&2
  exit 1
fi

rm -f "$PID_FILE"
echo "Killed."
