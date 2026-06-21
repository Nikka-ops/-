# Boss 直聘 Cookie 配置

InterviewRadar 通过 Boss 直聘 **搜索 API** 拉岗位列表，必须携带你在浏览器登录后的 Cookie（反爬要求）。

## 方式三：Chrome CDP（无需手抄 Cookie，推荐）

用 **Chrome DevTools Protocol** 复用浏览器登录态，不用从 Network 复制 Cookie。

```bash
# 1. 安装 CDP 依赖（一次性）
.venv/bin/pip install websocket-client
# 或: pip install -e ".[boss-cdp]"

# 2. 启动专用 Chrome（会打开 zhipin.com）
bash scripts/tools/start-boss-cdp-chrome.sh

# 3. 在打开的 Chrome 里登录 Boss 直聘

# 4. 验证
bash scripts/tools/check-boss-cdp.sh

# 5. 拉取
interview-radar-jobs --boss-cdp --keywords "AI应用" --max-per-query 10
```

未配 Cookie 时，若 CDP 端口 `9222` 已监听，也会 **自动尝试 CDP**。

环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BOSS_CDP_PORT` | `9222` | Chrome remote-debugging 端口 |
| `BOSS_CDP_PROFILE` | `~/.interview-radar/boss-chrome-profile` | 隔离登录态 |
| `BOSS_CDP=1` | - | 强制优先 CDP |

---

## 方式一：`.env`（Cookie，备选）

在项目根目录 `InterviewRadar/`：

```bash
cp .env.example .env
```

编辑 `.env`，填入一行（**整段 Cookie 不要换行**）：

```bash
BOSS_ZHIPIN_COOKIE=lastCity=101010100; wt2=...; __zp_stoken__=...; ...
```

保存后，以下命令会自动读取 `.env`（无需每次 `export`）：

- `interview-radar-jobs`
- `interview-radar-web`（Web UI 勾选 Boss 时）

也可用交互脚本：

```bash
bash scripts/tools/setup-boss-cookie.sh
```

## 方式二：临时 export

```bash
export BOSS_ZHIPIN_COOKIE='lastCity=101010100; ...'
interview-radar-jobs --sources boss_zhipin --keywords "AI应用" --max-per-query 5
```

别名环境变量：`INTERVIEWRADAR_BOSS_COOKIE`（与上面等价）。

## 从 Chrome 导出 Cookie（约 2 分钟）

1. 打开 [https://www.zhipin.com](https://www.zhipin.com) 并 **登录**（手机号 / 微信）。
2. 随便搜一次岗位，确保页面正常。
3. 按 `F12` 或 `Cmd+Option+I` 打开开发者工具。
4. 切到 **Network（网络）**，刷新页面。
5. 在列表里点任意请求（域名 `www.zhipin.com` 或 `zhipin.com`）。
6. 在 **Headers** 里找到 **Request Headers → Cookie**，复制 **整行**（很长，含分号）。
7. 粘贴到 `.env` 的 `BOSS_ZHIPIN_COOKIE=` 后面，或运行 `setup-boss-cookie.sh`。

**不要**把 Cookie 提交到 Git、发到群里或贴到工单里。

## 验证是否生效

```bash
interview-radar-doctor          # 应显示 Boss直聘 Cookie: configured
bash scripts/tools/check-boss-cookie.sh
```

成功时 `job_count > 0`；失败常见提示：

| 提示 | 处理 |
|------|------|
| 未配置 Cookie | 检查 `.env` 路径、变量名是否为 `BOSS_ZHIPIN_COOKIE` |
| Cookie 失效 / 环境异常 / code 37 | 重新登录 zhipin.com 再导出 Cookie |
| 未找到 npx | 与 Boss 无关；Boss 只需 Python + Cookie |

## Web UI

1. 配置好 `.env` 后 **重启 Web**：`bash start-web.sh`
2. ⚙ 设置 → 勾选 **「同时拉 Boss直聘」** → **拉取在招岗位**

## Cookie 有效期

Boss Cookie 通常 **几天到几周** 会过期。拉取突然变 0 条时，按上面步骤重新导出即可。

## 合规

仅个人求职调研；控制拉取频率；遵守 Boss 直聘用户协议。
