#!/usr/bin/env bash
# 关闭 CDP Chrome 并备份/清空专用 Profile（Boss 页闪退、登录异常时用）。
set -euo pipefail

PORT="${BOSS_CDP_PORT:-9222}"
PROFILE="${BOSS_CDP_PROFILE:-$HOME/.interview-radar/boss-chrome-profile}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "将关闭端口 ${PORT} 上的 CDP Chrome…"
PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
if [[ -n "$PIDS" ]]; then
  kill $PIDS 2>/dev/null || true
  sleep 2
  kill -9 $PIDS 2>/dev/null || true
  sleep 1
fi

if [[ -d "$PROFILE" ]]; then
  STAMP="$(date +%Y%m%d-%H%M%S)"
  BACKUP="${PROFILE}.bak-${STAMP}"
  echo "备份 Profile → $BACKUP"
  mv "$PROFILE" "$BACKUP"
fi

echo ""
echo "✓ 已重置。请重新启动:"
echo "  bash $ROOT/scripts/tools/start-boss-cdp-chrome.sh"
echo ""
echo "然后在弹出的专用 Chrome 里登录 Boss。"
