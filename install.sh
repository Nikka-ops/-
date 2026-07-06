#!/usr/bin/env bash
# One-time setup: venv + pip install -e .
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Creating .venv …"
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi

.venv/bin/pip install -U pip -q
.venv/bin/pip install -e ".[dev]" -q

echo ""
echo "✓ Installed. Commands (run from anywhere after):"
echo "  $ROOT/.venv/bin/interview-radar-web --port 8765"
echo "  $ROOT/start-web.sh"
echo ""
.venv/bin/interview-radar-doctor
