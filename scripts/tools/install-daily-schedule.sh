#!/usr/bin/env bash
# 跨平台安装入口（内部调用 Python）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m scripts.tools.install_daily_schedule "$@"
fi
exec python3 -m scripts.tools.install_daily_schedule "$@"
