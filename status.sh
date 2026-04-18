#!/usr/bin/env bash
# Report on the OSINT uvicorn server state:
# - is it running (via PID file or rogue process)?
# - which port is it listening on?
# - last ~20 lines of the log
#
# Usage: ./status.sh [--log-lines N]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.uvicorn.pid"
LOG_FILE="$ROOT/uvicorn.log"
LOG_LINES=20

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-lines)
      LOG_LINES="${2:?--log-lines requires a value}"
      shift
      ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

_show_port() {
  local pid="$1"
  # NOTE: -a forces AND semantics across the -i / -p filters on macOS; without
  # it lsof logical-ORs them and you end up matching every LISTEN socket on the
  # box, not just this process's.
  lsof -a -iTCP -sTCP:LISTEN -nP -p "$pid" 2>/dev/null \
    | sed -n 's/.*:\([0-9][0-9]*\)[[:space:]]*(LISTEN).*/\1/p' \
    | head -n 1
}

# Anchored regex that only matches a python-ish binary at the START of argv,
# not the wrapping shell whose argv happens to contain "python -m uvicorn..."
# as a quoted substring.
_UVICORN_RE='^[^ ]+[Pp]ython[^ ]* -m uvicorn web\.app:app'

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    ETIME=$(ps -p "$PID" -o etime= 2>/dev/null | tr -d ' ')
    PORT=$(_show_port "$PID")
    echo "State:   RUNNING"
    echo "PID:     $PID"
    echo "Port:    ${PORT:-unknown}"
    echo "Uptime:  $ETIME"
    echo "URL:     http://127.0.0.1:${PORT:-8000}/"
    echo
    if [[ -f "$LOG_FILE" ]]; then
      echo "Last $LOG_LINES log lines ($LOG_FILE):"
      echo "----"
      tail -n "$LOG_LINES" "$LOG_FILE"
    else
      echo "(no log file yet at $LOG_FILE)"
    fi
    exit 0
  fi
  echo "State:   STOPPED (stale PID file at $PID_FILE, process not alive)"
  exit 0
fi

if pgrep -f "$_UVICORN_RE" >/dev/null; then
  echo "State:   UNTRACKED (not managed by ./start.sh but uvicorn is running)"
  while read -r rpid; do
    [[ -z "$rpid" ]] && continue
    rport=$(_show_port "$rpid")
    retime=$(ps -p "$rpid" -o etime= 2>/dev/null | tr -d ' ')
    echo "  PID $rpid  PORT ${rport:-?}  UPTIME ${retime:-?}"
  done < <(pgrep -f "$_UVICORN_RE")
  exit 0
fi

echo "State:   STOPPED"
