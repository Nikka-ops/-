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
  echo "CDP 端口 $PORT 已在监听（Chrome 已在跑）。"
  echo ""
  echo "⚠  不要再次启动 start-boss-cdp-chrome.sh — 同一 Profile 开第二个窗口会闪退。"
  echo "   请改用: bash scripts/tools/focus-boss-cdp-chrome.sh"
  echo ""
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    (cd "$ROOT" && "$ROOT/.venv/bin/python" - <<'PY') 2>/dev/null || true
from scripts.config import bootstrap_env, boss_cdp_port
from scripts.jobs.cdp_client import cdp_list_targets, open_zhipin_page

bootstrap_env()
port = boss_cdp_port()
has_zhipin = any("zhipin.com" in str(t.get("url") or "") for t in cdp_list_targets(port))
if not has_zhipin:
    open_zhipin_page(port, wait_sec=3.0)
    print("已在 CDP Chrome 打开 Boss 职位页。")
else:
    print("CDP Chrome 里已有 Boss 标签页。")
PY
  fi
  if [[ "$(uname)" == "Darwin" ]]; then
    osascript <<'APPLESCRIPT' 2>/dev/null || true
tell application "Google Chrome"
  repeat with w in windows
    set wt to name of w
    if wt contains "BOSS" or wt contains "直聘" or wt contains "zhipin" then
      set index of w to 1
      exit repeat
    end if
  end repeat
  activate
end tell
APPLESCRIPT
  fi
else
  echo "启动 Chrome CDP → 端口 $PORT"
  echo "Profile: $PROFILE"
  JOBS_URL="https://www.zhipin.com/web/geek/jobs"
  echo "将打开专用 Chrome（Profile: $PROFILE）"
  "$CHROME" \
    --remote-debugging-port="$PORT" \
    --remote-allow-origins=* \
    --user-data-dir="$PROFILE" \
    --no-first-run \
    --no-default-browser-check \
    --new-window \
    "$JOBS_URL" &
  sleep 3
  if [[ "$(uname)" == "Darwin" ]]; then
    osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null || true
  fi
fi

echo ""
echo "识别 CDP Chrome：窗口标题含 BOSS / 直聘 的那个（专用 Profile）。"
echo "  不是日常 Chrome；Cookie 需在此窗口单独登录 Boss。"
echo "  若 Boss 页闪退: bash scripts/tools/reset-boss-cdp-chrome.sh 后重开"
echo "  若已在跑: bash scripts/tools/focus-boss-cdp-chrome.sh（勿重复 start）"
echo ""
echo "环境变量（可选）:"
echo "  BOSS_CDP_PORT=$PORT"
echo "  BOSS_CDP=1   # 强制优先 CDP"
