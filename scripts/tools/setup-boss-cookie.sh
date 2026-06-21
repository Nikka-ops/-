#!/usr/bin/env bash
# Write BOSS_ZHIPIN_COOKIE into project .env (never commit .env).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../" && pwd)"
ENV_FILE="$ROOT/.env"

echo "Boss 直聘 Cookie 配置"
echo "  1. 浏览器登录 https://www.zhipin.com"
echo "  2. 开发者工具 → Network → 任意请求 → Headers → Cookie"
echo "  3. 复制整段 Cookie 粘贴到下面（输入结束按 Enter）："
echo ""
read -r -p "Cookie: " COOKIE

if [[ -z "${COOKIE// }" ]]; then
  echo "未输入 Cookie，退出。"
  exit 1
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^BOSS_ZHIPIN_COOKIE=' "$ENV_FILE"; then
  # macOS sed
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s|^BOSS_ZHIPIN_COOKIE=.*|BOSS_ZHIPIN_COOKIE=${COOKIE}|" "$ENV_FILE"
  else
    sed -i '' "s|^BOSS_ZHIPIN_COOKIE=.*|BOSS_ZHIPIN_COOKIE=${COOKIE}|" "$ENV_FILE"
  fi
else
  {
    echo ""
    echo "# Boss直聘（勿提交 Git）"
    echo "BOSS_ZHIPIN_COOKIE=${COOKIE}"
  } >> "$ENV_FILE"
fi

echo ""
echo "✓ 已写入 $ENV_FILE"
echo "验证: bash $ROOT/scripts/tools/check-boss-cookie.sh"
echo "Web:  重启 bash start-web.sh 后在设置里勾选 Boss"
