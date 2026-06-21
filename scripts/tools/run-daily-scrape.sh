#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m scripts.tools.run_daily_scrape "$@"
fi
exec python3 -m scripts.tools.run_daily_scrape "$@"
