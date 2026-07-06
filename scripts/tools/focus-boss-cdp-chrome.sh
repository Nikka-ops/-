#!/usr/bin/env bash
# 聚焦已在跑的 CDP Chrome，并打开 Boss 职位页（不会启动第二个 Chrome，避免闪退）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PORT="${BOSS_CDP_PORT:-9222}"

if ! curl -sf "http://127.0.0.1:${PORT}/json/version" >/dev/null; then
  echo "✗ CDP 未启动。请先运行:"
  echo "  bash scripts/tools/start-boss-cdp-chrome.sh"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Run bash install.sh first."
  exit 1
fi

.venv/bin/python - <<'PY'
from scripts.config import bootstrap_env, boss_cdp_port
from scripts.jobs.cdp_client import cdp_list_targets, find_zhipin_page_ws, open_zhipin_page

bootstrap_env()
port = boss_cdp_port()
ws = find_zhipin_page_ws(port) or open_zhipin_page(port, wait_sec=3.0)
for t in cdp_list_targets(port):
    if t.get("type") != "page":
        continue
    url = str(t.get("url") or "")
    if "zhipin.com" in url:
        print("Boss 标签:", url[:90])
        break
else:
    print("已尝试打开 Boss 职位页")
PY

if [[ "$(uname)" == "Darwin" ]]; then
  osascript <<'APPLESCRIPT' 2>/dev/null || osascript -e 'tell application "Google Chrome" to activate'
tell application "Google Chrome"
  set found to false
  repeat with w in windows
    set wt to name of w
    if wt contains "BOSS" or wt contains "直聘" or wt contains "zhipin" then
      set index of w to 1
      set found to true
      exit repeat
    end if
  end repeat
  activate
end tell
APPLESCRIPT
fi

echo ""
echo "✓ 请在标题含 BOSS/直聘 的 Chrome 窗口操作（专用 Profile，需单独登录）。"
echo "  职位页: https://www.zhipin.com/web/geek/jobs"
echo "  勿再运行 start-boss-cdp-chrome.sh（会尝试开第二个窗口并闪退）。"
