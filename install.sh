#!/usr/bin/env bash
# One-time setup: venv + pip install -e .
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Pick a Python >= 3.11; fail early with a clear message otherwise.
choose_python() {
  for py in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      if "$py" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
        echo "$py"; return 0
      fi
    fi
  done
  have="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo none)"
  echo "✗ 需要 Python >= 3.11，但当前只找到 $have。请先安装 Python 3.11+（https://www.python.org/downloads/）后重试。" >&2
  return 1
}

if [[ ! -d .venv ]]; then
  PYTHON_BIN="$(choose_python)" || exit 1
  echo "Creating .venv with $PYTHON_BIN …"
  "$PYTHON_BIN" -m venv .venv
fi

# Validate an existing .venv too — a stale 3.9/3.10 venv would fail later.
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
