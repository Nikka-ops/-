#!/usr/bin/env bash
# 启动带 CDP 的 Chrome，用于 Boss 直聘（无需手抄 Cookie）。
set -euo pipefail

PORT="${BOSS_CDP_PORT:-9222}"
PROFILE="${BOSS_CDP_PROFILE:-$HOME/.interview-radar/boss-chrome-profile}"
URL="https://www.zhipin.com/"

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
  echo "CDP 端口 $PORT 已在监听。"
  echo "若尚未登录 Boss，请在已打开的 Chrome 中访问 $URL 并登录。"
else
  echo "启动 Chrome CDP → 端口 $PORT"
  echo "Profile: $PROFILE"
  JOBS_URL="https://www.zhipin.com/web/geek/jobs?query=AI应用"
  if [[ "$(uname)" == "Darwin" ]]; then
    # open -na 会弹出独立窗口（专用 profile），比后台二进制更易看见
    open -na "Google Chrome" --args \
      --remote-debugging-port="$PORT" \
      --remote-allow-origins=* \
      --user-data-dir="$PROFILE" \
      --no-first-run \
      --no-default-browser-check \
      --new-window \
      "$JOBS_URL"
    sleep 3
    osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null || true
  else
    "$CHROME" \
      --remote-debugging-port="$PORT" \
      --remote-allow-origins=* \
      --user-data-dir="$PROFILE" \
      --no-first-run \
      --no-default-browser-check \
      "$JOBS_URL" &
    sleep 2
  fi
fi

echo ""
echo "下一步:"
echo "  1. 在打开的 Chrome 中登录 Boss 直聘（若未登录）"
echo "  2. 验证: bash scripts/tools/check-boss-cdp.sh"
echo "  3. 拉取: interview-radar-jobs --boss-cdp --keywords 'AI应用' --max-per-query 10"
echo ""
echo "环境变量（可选）:"
echo "  BOSS_CDP_PORT=$PORT"
echo "  BOSS_CDP=1   # 强制优先 CDP"
