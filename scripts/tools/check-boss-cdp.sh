#!/usr/bin/env bash
# Smoke test Boss CDP fetch (needs Chrome on BOSS_CDP_PORT + zhipin login).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../" && pwd)"
cd "$ROOT"

PORT="${BOSS_CDP_PORT:-9222}"
if ! curl -sf "http://127.0.0.1:${PORT}/json/version" >/dev/null; then
  echo "✗ CDP 未启动（端口 $PORT）"
  echo "  运行: bash scripts/tools/start-boss-cdp-chrome.sh"
  exit 1
fi

if [[ ! -x .venv/bin/interview-radar-jobs ]]; then
  echo "Run bash install.sh first."
  exit 1
fi

.venv/bin/pip install -q websocket-client 2>/dev/null || true

echo "Testing Boss CDP (max 3) …"
OUT="$(.venv/bin/interview-radar-jobs \
  --boss-cdp \
  --sources boss_zhipin \
  --no-job-pro \
  --keywords "AI" \
  --max-per-query 3 \
  --json 2>&1)" || true

COUNT="$(echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('job_count',0))" 2>/dev/null || echo 0)"
if [[ "$COUNT" -ge 1 ]]; then
  echo "✓ Boss CDP 有效，岗位数: $COUNT"
  echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); j=d['jobs'][0]; print('  sample:', j.get('title'), '|', j.get('company'))" 2>/dev/null
  exit 0
fi

echo "✗ Boss CDP 未拉到岗位（请确认 Chrome 已登录 zhipin.com）"
echo "$OUT" | python3 -m json.tool 2>/dev/null | head -40 || echo "$OUT"
exit 1
