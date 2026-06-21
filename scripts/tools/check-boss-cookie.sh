#!/usr/bin/env bash
# Quick smoke test for Boss Zhipin cookie (2 jobs max).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/interview-radar-jobs ]]; then
  echo "Run bash install.sh first."
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

if [[ -z "${BOSS_ZHIPIN_COOKIE:-}${INTERVIEWRADAR_BOSS_COOKIE:-}" ]]; then
  echo "✗ 未配置 BOSS_ZHIPIN_COOKIE"
  echo "  运行: bash scripts/tools/setup-boss-cookie.sh"
  echo "  或见: docs/setup/boss-zhipin-cookie.md"
  exit 1
fi

echo "Testing Boss直聘 search (max 2) …"
OUT="$(.venv/bin/interview-radar-jobs \
  --sources boss_zhipin \
  --no-job-pro \
  --keywords "AI" \
  --max-per-query 2 \
  --json 2>&1)" || true

if echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('job_count',0))" 2>/dev/null | grep -q '^[1-9]'; then
  echo "✓ Boss直聘 Cookie 有效"
  echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  jobs:', d['job_count']); print('  sample:', d['jobs'][0]['title'] if d.get('jobs') else '')"
  exit 0
fi

echo "✗ Boss 拉取失败"
echo "$OUT" | python3 -m json.tool 2>/dev/null || echo "$OUT"
exit 1
