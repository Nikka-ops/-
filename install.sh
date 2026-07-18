#!/usr/bin/env bash
# One-time setup: venv + pip install -e .
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

choose_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    printf '%s\n' "python3.11"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.11+ is required but python3 was not found." >&2
    return 1
  fi
  if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    echo "Python 3.11+ is required. Found: $(python3 --version 2>&1)" >&2
    return 1
  fi
  printf '%s\n' "python3"
}

PYTHON_BIN="$(choose_python)"

if [[ ! -d .venv ]]; then
  echo "Creating .venv …"
  "$PYTHON_BIN" -m venv .venv
fi

if ! .venv/bin/python - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "Existing .venv uses $(.venv/bin/python --version 2>&1), but Python 3.11+ is required." >&2
  echo "Remove .venv and rerun install.sh to recreate it with a supported interpreter." >&2
  exit 1
fi

.venv/bin/pip install -U pip -q
.venv/bin/pip install -e ".[dev]" -q

echo ""
echo "✓ Installed. Commands (run from anywhere after):"
echo "  $ROOT/.venv/bin/interview-radar-web --port 8765"
echo "  $ROOT/start-web.sh"
echo ""
.venv/bin/interview-radar-doctor
