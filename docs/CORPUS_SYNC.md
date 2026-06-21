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

## 全量建库（首次或大补）

单岗位（推荐先跑 AI 应用）：

```bash
uv run python -m scripts.tools.full_scrape --role-id ai_app --companies all --skip-xhs
```

多岗位依次全量（共享牛客滚动库，各自重建 bank）：

```bash
uv run python -m scripts.tools.full_scrape --role-id backend --companies all --skip-xhs
uv run python -m scripts.tools.full_scrape --role-id algorithm --companies all --skip-xhs
```

断点续跑牛客搜索词：

```bash
uv run python -m scripts.tools.full_scrape --role-id ai_app --companies all --resume --skip-xhs
```

常用环境变量（`.env`）：

| 变量 | 含义 |
|------|------|
| `FULL_SCRAPE_RECENCY_DAYS` | 时效窗口（默认 365） |
| `POST_AI_FILTER=1` | 规则 + DeepSeek 混合过滤 |
| `DEEPSEEK_API_KEY` | AI 过滤 API Key |
| `XHS_WEB_SESSION` | 小红书 cookie（不配则跳过 live 抓取） |

## 每日增量

**单岗位**（默认 `ai_app`）：

```bash
uv run python -m scripts.tools.daily_scrape --role-id ai_app --companies all --skip-xhs
```

**多岗位**：抓取一次（合并关键词），分别重建多个 bank：

```bash
uv run python -m scripts.tools.daily_scrape \
  --role-ids ai_app,backend,algorithm \
  --companies all \
  --skip-xhs
```

仅重建、不抓取：

```bash
uv run python -m scripts.tools.daily_scrape \
  --role-ids ai_app,backend \
  --companies all \
  --skip-xhs \
  --skip-nowcoder
```

### 定时任务

```bash
# 安装（macOS launchd / Linux cron / Windows 任务计划）
uv run python -m scripts.tools.install_daily_schedule \
  --role-ids ai_app,backend \
  --hour 8 --minute 0

# 手动试跑
uv run python -m scripts.tools.run_daily_scrape
```

环境变量：

| 变量 | 含义 |
|------|------|
| `INTERVIEWRADAR_DAILY_ROLE_ID` | 单岗位（与 `ROLE_IDS` 二选一） |
| `INTERVIEWRADAR_DAILY_ROLE_IDS` | 逗号分隔多岗位，如 `ai_app,backend` |
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
