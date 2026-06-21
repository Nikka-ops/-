#!/usr/bin/env bash
# Start Web UI — auto-install if needed; auto-pick port if busy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REQUESTED_PORT="${1:-8765}"

if [[ ! -x .venv/bin/interview-radar-web ]]; then
  echo "First run — installing …"
  bash "$ROOT/install.sh"
fi

port_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

PORT="$REQUESTED_PORT"
if ! port_free "$PORT"; then
  echo "Port ${PORT} is in use."
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "InterviewRadar may already be running → http://127.0.0.1:${PORT}/"
    echo "To stop it: kill \$(lsof -ti :${PORT})"
    echo "Or start on another port: bash start-web.sh 8767"
    exit 0
  fi
  for p in $(seq "$REQUESTED_PORT" $((REQUESTED_PORT + 20))); do
    if port_free "$p"; then
      PORT="$p"
      echo "Using free port ${PORT} instead."
      break
    fi
  done
  if ! port_free "$PORT"; then
    echo "No free port found (${REQUESTED_PORT}–$((REQUESTED_PORT + 20)))."
    echo "Stop the old process: kill \$(lsof -ti :${REQUESTED_PORT})"
    exit 1
  fi
fi

echo "InterviewRadar Web UI: http://127.0.0.1:${PORT}/"
echo "Press Ctrl+C to stop."
exec .venv/bin/interview-radar-web --port "$PORT"
