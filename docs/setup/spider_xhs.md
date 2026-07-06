# 小红书面经采集 — Spider_XHS

面经主源使用 [Spider_XHS](https://github.com/cv-cat/Spider_XHS)（HTTP API + 签名）。

> 仅供个人学习交流，请遵守平台服务条款。

## 长期增量（推荐）

**两段式**：低频联网抓 JSON → 日常只读本地 JSON 入库。不要每次 `full_scrape` 直连抓。

| 阶段 | 做什么 | 频率 |
|------|--------|------|
| 1. 抓取 | Spider_XHS 搜词 → JSON | 默认 24 词/次；`--core-only` 26 核心词/次 |
| 2. 入库 | 读本地 JSON + 建 bank | 同上（自动） |

### 一次性准备

```bash
git clone https://github.com/cv-cat/Spider_XHS.git ~/.spider_xhs
cd ~/.spider_xhs && npm install
cd /path/to/data-agent-radar && .venv/bin/pip install -e ".[xhs]"
bash scripts/tools/start-xhs-cdp-chrome.sh   # 专用小号扫码登录，窗口常开
```

`.env` 默认档（24 词/次）：

```bash
XHS_DAILY_KEYWORDS_PER_DAY=24
XHS_MAX_KEYWORDS_PER_RUN=32
XHS_BATCH_PAUSE_SECONDS=30
POST_AI_FILTER=1
```

### 日常命令

```bash
# 抓取前自检（461 = 被拦截）
.venv/bin/python -m scripts.tools.xhs_session_check

# 正常：抓今日词 + 重建面经库
.venv/bin/python -m scripts.tools.xhs_incremental --role-id data --core-only

# 被 461 拦截：跳过抓取，只用已有 JSON 入库
.venv/bin/python -m scripts.tools.xhs_incremental --role-id data --import-only
```

cron 示例：

```bash
bash scripts/tools/cron-xhs-incremental.sh
```

多岗位仍可用 `daily_scrape`（小红书 + 牛客 + JD）：

```bash
.venv/bin/python -m scripts.tools.daily_scrape --role-ids data,ai_app --companies all
```

### 首次全量补历史

只在账号正常时跑 **一次**，之后改走 `xhs_incremental`：

```bash
.venv/bin/python -m scripts.tools.xhs_scrape_safe --role-id data --pause 60
POST_AI_FILTER=1 .venv/bin/python -m scripts.tools.full_scrape \
  --role-id data --companies all --skip-xhs --fast-rebuild
```

## 登录

```bash
bash scripts/tools/start-xhs-cdp-chrome.sh
```

在专用 Chrome 扫码登录；抓取前在浏览器**手动搜一次**确认有结果。

## 环境变量

| 变量 | 说明 |
|------|------|
| `SPIDER_XHS_HOME` | 默认 `~/.spider_xhs` |
| `XHS_COOKIES` | 完整 Cookie（DevTools 复制，优于仅 web_session） |
| `XHS_CDP=1` | 从 CDP 9233 读 Cookie（默认） |
| `XHS_DAILY_KEYWORDS_PER_DAY` | 每日轮转词数，默认 `24` |

## 故障排查

| 现象 | 处理 |
|------|------|
| HTTP **461** / 全 0 条 | 风控或 Cookie 失效；浏览器手动搜 → 换小号/等 24h → `--import-only` 用旧 JSON |
| `Cannot find module 'crypto-js'` | `cd ~/.spider_xhs && npm install` |
| 入库太少 | 放宽 `POST_AI_FILTER` 或看 `scrape_diagnose` 漏斗 |
