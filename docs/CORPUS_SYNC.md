# 面经语料：目录、多岗位、增量与 Fork 同步

InterviewRadar 的**代码在 Git 仓库**，**面经数据在本地 `corpus_cache/`**（默认 gitignored，体积可达数百 MB）。本文说明如何建库、增量更新、扩展公司名归一化，以及 fork 后如何同步数据。

## 目录结构

```text
corpus_cache/                          # 可用 INTERVIEWRADAR_CACHE_DIR 改路径
├── banks/                             # 各岗位 question bank
│   └── AI_应用开发__…_<hash>/
│       ├── question_bank.json
│       ├── meta.json
│       └── agent_handoff.md
├── daily/
│   ├── rolling_nowcoder_posts.json    # 牛客滚动库（多岗位共享）
│   ├── scrape_state.json              # 增量状态（词轮询、已见 URL）
│   ├── post_ai_filter_cache.json      # DeepSeek 面经过滤缓存
│   └── cron.log                       # 定时任务日志
└── assets/xhs/                        # 小红书图片 OCR 缓存
```

- **一个岗位 = 一个 bank 目录**（由 `role_id` + 公司列表 + 配置 hash 决定 slug）。
- **牛客滚动库是共享的**：daily 增量只抓一次，多岗位分别 `run_pipeline` 重建各自 bank。
- Web UI 切换岗位下拉框时，只展示**已有 bank** 的数据；新岗位需先建库。

## 当前聚焦岗位

默认只抓取并展示 **数据开发/数仓**（`data`）与 **Agent 开发**（`ai_app`）。可通过环境变量扩展：

| 变量 | 默认 | 含义 |
|------|------|------|
| `INTERVIEWRADAR_FOCUS_ROLE_IDS` | `data,ai_app` | Web UI 可见岗位、JD 默认拉取范围 |
| `INTERVIEWRADAR_DAILY_ROLE_IDS` | `data,ai_app` | 每日增量面经抓取岗位 |

## 面经主源：小红书

面经语料**优先保障小红书**（图片面经、时效性好）。使用前请在 `.env` 配置：

```bash
XHS_WEB_SESSION=<浏览器 cookie 中的 web_session 值>
```

可选调优：

| 变量 | 默认 | 含义 |
|------|------|------|
| `XHS_DAILY_KEYWORDS_PER_DAY` | `12` | 每日增量抓取词数（主源） |
| `XHS_MAX_KEYWORDS_PER_RUN` | `12` | 全量/分批每轮词数 |
| `NOWCODER_DAILY_QUERIES_PER_DAY` | `12` | 牛客补充词数（次源） |
| `XHS_MIN_POSTS_SKIP_NOWCODER` | `5` | 小红书帖 ≥ 此数时跳过牛客联网 |

牛客滚动库为**补充**；建库时 `xhs_priority=true`，小红书帖足够时不合并牛客增量。

## 全量建库（首次或大补）

**先配 `XHS_WEB_SESSION`**，再跑（小红书先抓、牛客补充）：

```bash
uv run python -m scripts.tools.full_scrape --role-id data --companies all
uv run python -m scripts.tools.full_scrape --role-id ai_app --companies all
```

仅补牛客（不推荐，缺主源）：

```bash
uv run python -m scripts.tools.full_scrape --role-id data --companies all --skip-xhs
```

断点续跑牛客搜索词：

```bash
uv run python -m scripts.tools.full_scrape --role-id data --companies all --resume
```

常用环境变量（`.env`）：

| 变量 | 默认 | 含义 |
|------|------|------|
| `FULL_SCRAPE_RECENCY_DAYS` | `90` | 面经时效（近 3 个月） |
| `XHS_EXPORT_MAX_AGE_DAYS` | `90` | 本地小红书 JSON 有效期 |
| `XHS_BATCH_PAUSE_SECONDS` | `30` | 小红书批间暂停（秒） |
| `XHS_DAILY_KEYWORDS_PER_DAY` | `24` | 每日增量词数 |
| `XHS_MAX_KEYWORDS_PER_RUN` | `16` | 全量每轮词数 |
| `JOB_RECENCY_DAYS` | `90` | 官网 JD 发布日期窗口 |
| `POST_AI_FILTER=1` | 入库前 DeepSeek 质检：是否面经 + 归属 `data`/`ai_app`（有 KEY 时默认开） |
| `DEEPSEEK_API_KEY` | AI 过滤 API Key |
| `XHS_WEB_SESSION` | **必填（面经主源）** — 小红书 cookie |

## 每日增量

**默认两岗位**（`data` + `ai_app`；**先抓小红书**，牛客补充）：

```bash
uv run python -m scripts.tools.daily_scrape --companies all
```

显式指定：

```bash
uv run python -m scripts.tools.daily_scrape \
  --role-ids data,ai_app \
  --companies all
```

仅重建、不抓取：

```bash
uv run python -m scripts.tools.daily_scrape \
  --role-ids data,ai_app \
  --companies all \
  --skip-xhs \
  --skip-nowcoder
```

### 岗位 JD

```bash
# 同时拉取两岗位 JD（Boss / 官网 / job-pro）
uv run interview-radar-jobs --companies 字节跳动 腾讯 --no-boss

# 或显式
uv run interview-radar-jobs --role-ids data,ai_app --companies all --no-boss
```

### 定时任务

```bash
# 安装（macOS launchd / Linux cron / Windows 任务计划）
uv run python -m scripts.tools.install_daily_schedule \
  --role-ids data,ai_app \
  --hour 8 --minute 0

# 手动试跑
uv run python -m scripts.tools.run_daily_scrape
```

环境变量：

| 变量 | 含义 |
|------|------|
| `INTERVIEWRADAR_DAILY_ROLE_ID` | 单岗位（与 `ROLE_IDS` 二选一） |
| `INTERVIEWRADAR_DAILY_ROLE_IDS` | 逗号分隔多岗位，默认 `data,ai_app` |
| `INTERVIEWRADAR_FOCUS_ROLE_IDS` | Web/JD 聚焦岗位，默认 `data,ai_app` |
| `INTERVIEWRADAR_DAILY_COMPANIES` | 默认 `all` |
| `INTERVIEWRADAR_CACHE_DIR` | 语料根目录 |

## 公司名归一化（扩展「其他」过滤）

映射配置在 **`config/company_aliases.yaml`**（进 Git，可 PR）：

```yaml
subsidiaries:
  淘天: 阿里巴巴
  WXG: 腾讯
  TikTok: 字节跳动

not_companies:
  - ai
  - agent
  - 27实习
```

- 运行时由 `scripts/corpus/company_normalize.py` 加载。
- 自定义路径：`COMPANY_ALIASES_PATH=/path/to/aliases.yaml`
- 改 YAML 后重建 bank 即可生效；**无需**重抓原始帖。

贡献流程：发现 UI「其他」里仍有误识别公司 → 编辑 YAML → 提 PR。

## Fork 后如何同步数据

代码与数据分离，任选一种：

| 方式 | 适用 |
|------|------|
| **各自抓取** | 有牛客/小红书访问能力；跑 `full_scrape` + `daily_scrape` |
| **共享 cache 目录** | 团队内网 NAS；统一设 `INTERVIEWRADAR_CACHE_DIR` |
| **Git LFS / 独立 data 仓库** | 定期发布 tarball / Release 附件 |
| **仅示例库** | 用 `examples/sample_raw_posts.json` 离线 demo |

Fork 者 `git pull` 只会同步**规则与代码**（含 `company_aliases.yaml`），不会同步几百 MB 面经。需要数据时请按上表单独同步 `corpus_cache/` 或自行抓取。

## 诊断

```bash
uv run python -m scripts.tools.scrape_diagnose --role-id ai_app --companies all
uv run interview-radar-doctor
```

查看最近一次 daily 结果：`corpus_cache/daily/last_run.json`。
