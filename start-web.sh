#!/usr/bin/env bash
# Start Web UI — auto-install if needed; auto-pick port if busy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REQUESTED_PORT="8765"
OPEN_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --open)
      OPEN_BROWSER=1
      ;;
    *)
      REQUESTED_PORT="$arg"
      ;;
  esac
done

if [[ ! -x .venv/bin/python ]]; then
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
if [[ "$OPEN_BROWSER" -eq 0 ]]; then
  exec .venv/bin/python -m scripts.api.server --port "$PORT"
fi

.venv/bin/python -m scripts.api.server --port "$PORT" &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

URL="http://127.0.0.1:${PORT}/"
if command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi

wait "$SERVER_PID"
