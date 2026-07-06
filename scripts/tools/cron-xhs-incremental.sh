#!/usr/bin/env bash
# 小红书长期增量 cron：核心词全扫 + 短间隔（可 crontab 早/午/晚各 1 次）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

if ! "$PY" -m scripts.tools.xhs_session_check; then
  echo "会话不可用，仅本地入库…"
  exec "$PY" -m scripts.tools.xhs_incremental --role-id data --import-only
fi

exec "$PY" -m scripts.tools.xhs_incremental --role-id data --core-only --aggressive
