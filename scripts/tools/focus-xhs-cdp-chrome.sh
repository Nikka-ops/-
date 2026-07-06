#!/usr/bin/env bash
# 聚焦已运行的小红书 CDP Chrome（勿重复 start）。
set -euo pipefail

PORT="${XHS_CDP_PORT:-9233}"

if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "小红书 CDP 未启动（端口 $PORT）。请先运行:"
  echo "  bash scripts/tools/start-xhs-cdp-chrome.sh"
  exit 1
fi

if [[ "$(uname)" == "Darwin" ]]; then
  osascript <<'APPLESCRIPT' 2>/dev/null || true
tell application "Google Chrome"
  repeat with w in windows
    set wt to name of w
    if wt contains "小红书" or wt contains "xiaohongshu" or wt contains "rednote" then
      set index of w to 1
      exit repeat
    end if
  end repeat
  activate
end tell
APPLESCRIPT
  echo "已尝试聚焦小红书 Chrome 窗口（端口 $PORT）。"
else
  echo "CDP 端口 $PORT 在监听。请在 Chrome 中切换到小红书标签页。"
fi
