#!/usr/bin/env bash
# 启动专用 CDP Chrome 抓取小红书（真浏览器、独立 Profile，避免 Playwright 闪退）。
set -euo pipefail

PORT="${XHS_CDP_PORT:-9233}"
PROFILE="${XHS_CDP_PROFILE:-$HOME/.interview-radar/xhs-chrome-profile}"
URL="https://www.xiaohongshu.com/"

if [[ "$(uname)" == "Darwin" ]]; then
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  [[ -x "$CHROME" ]] || CHROME="/Applications/Chromium.app/Contents/MacOS/Chromium"
else
  CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
fi

if [[ -z "$CHROME" || ! -x "$CHROME" ]]; then
  echo "未找到 Chrome/Chromium。请安装 Google Chrome。"
  exit 1
fi

mkdir -p "$PROFILE"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "小红书 CDP 端口 $PORT 已在监听。"
  echo ""
  echo "⚠  不要重复 start — 同一 Profile 再开第二个窗口会闪退。"
  echo "   请改用: bash scripts/tools/focus-xhs-cdp-chrome.sh"
  echo ""
else
  echo "启动小红书专用 Chrome → CDP 端口 $PORT"
  echo "Profile: $PROFILE"
  "$CHROME" \
    --remote-debugging-port="$PORT" \
    --remote-allow-origins=* \
    --user-data-dir="$PROFILE" \
    --no-first-run \
    --no-default-browser-check \
    --new-window \
    "$URL" &
  sleep 3
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
fi

echo ""
echo "请在【专用 Chrome 窗口】用手机扫码登录小红书（仅首次）。"
echo "  勿关窗口；抓取时 Spider_XHS 会复用此登录态。"
echo "  若闪退: 先关所有该 Profile 窗口，再重跑本脚本。"
echo ""
echo "环境变量: XHS_CDP_PORT=$PORT  XHS_CDP=1（默认）"
echo "开始抓取: .venv/bin/python -m scripts.tools.full_scrape --role-id data --companies all --skip-nowcoder"
