<div align="center">

<img src="assets/logo.png" alt="InterviewRadar" width="200"/>

# InterviewRadar · 面试雷达

**基于真实面经,从你的简历自动生成项目锚定的个性化中文面试备考包**

[![tests](https://github.com/KunChen1110/InterviewRadar/actions/workflows/tests.yml/badge.svg)](https://github.com/KunChen1110/InterviewRadar/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](#)
[![Claude/Codex](https://img.shields.io/badge/Agent-Claude%20Code%20%2F%20Codex-purple.svg)](#)

</div>

---

## 它解决什么问题

市面上的"面试题库"几乎都是静态的,而面试官手里的题是动态的、时效的、个性化的。

- 你刷的 1000 道八股题里,**真正会被问到的可能不到 10%**——因为面试官是按你简历来问的,不是按题库目录
- 牛客 / 小红书的真实面经满天飞,但**没人帮你从里面挖出"跟你简历相关、且最近半年高频"的那一小撮**
- LLM 直接生成的面试题听起来像那么回事,但**没法溯源**——你不知道这道题真有人被问过吗

InterviewRadar 是一个可给 Claude Code 或 Codex 使用的面试准备工作流,把"你给的"变成"它给你的":

| 你给的 | 它做的 | 它给你的 |
|---|---|---|
| • 简历(PDF / 图片 / 扫描件)<br>• 一句**模糊**岗位方向<br>&nbsp;&nbsp;&nbsp;&nbsp;(例:"AI 应用开发""市场实习")<br>• 意向公司(可选) | • **仅**从牛客 + 小红书抓取真实面经<br>• 按**公司 × 岗位**分类整理<br>• 近两年时效**硬过滤**<br>• 频次 × 时效加权排序<br>• 把每道高频题尝试**挂到你简历里的项目**上<br>• LLM 推理 + Python 脚本各司其职 | • 一份中文 Markdown **备考包**<br>• **可追溯**的、锚定到你项目的<br>&nbsp;&nbsp;&nbsp;&nbsp;**连环追问链**<br>• 按公司与岗位分组的高频题 |

## 看一眼输出

> 给一份"3 个项目、目标 Agent 应用开发岗"的简历,跑出来长这样(节选):

```markdown
## 2. 简历 ↔ 岗位 Gap 分析

| 维度 | 现状 | 评级 |
|---|---|---|
| Agent Orchestration | P1 已实现多阶段状态机 | ✅ 强 |
| MCP 协议 | 简历未提 | ❌ 弱 |
| Function Calling 工程细节 | 没专门讲 | ⚠️ 中 |
...

## 4. 个性化项目追问链(锚到你的简历)

### 链 4.1 — 高频题 #3 → P1 多阶段状态机

> Q1: "你 P1 项目里设计了 Understanding → Diagnose → ... 这套状态机,
>      具体是怎么拆解出这六个阶段的?"
> Q2: "这套流程对应 ReAct / Plan-and-Execute / Reflexion 里的哪种范式?"
> Q3: "哪个阶段最容易出问题?你是怎么调的?"
```

完整样例:见 [`examples/sample_prep_package.md`](examples/sample_prep_package.md)

## 快速开始（开源 / 本地）

> 详细步骤见 [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md)

```bash
git clone https://github.com/KunChen1110/InterviewRadar.git
cd InterviewRadar
bash install.sh
bash start-web.sh          # → http://127.0.0.1:8765/
```

或手动：` .venv/bin/interview-radar-web --port 8765 `（需先 `bash install.sh`）

**30 秒离线体验**（在项目目录内）:

```bash
bash demo-bank.sh
# 或
.venv/bin/interview-radar --role "AI 应用开发" --from-report \
  --raw-posts examples/sample_raw_posts.json --bank-only
```

产出在 `corpus_cache/banks/<slug>/`：`question_bank.json` + `agent_handoff.md`。正式备考包 `prep_package.md` 需让 Cursor / Claude Code / Codex 读 `agent_handoff.md` 并按 `SKILL.md` 步骤 4–8 撰写（或 `--prep-mode heuristic` 看规则预览）。

**拉取在招岗位 JD**（Boss直聘 + 大厂官网，与面经库独立）:

```bash
.venv/bin/interview-radar-jobs --role-id ai_app --companies 字节跳动
```

Boss 需配置 `BOSS_ZHIPIN_COOKIE`；字节官网默认可用。详见 [`docs/setup/job-sources.md`](docs/setup/job-sources.md)。

### Web UI

```bash
cd InterviewRadar
bash start-web.sh
```

浏览器打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)

### 与 AI Agent 配合（推荐完整体验）

| 方式 | 说明 |
|------|------|
| **Cursor** | 在本仓库工作区，让 Agent 读 `SKILL.md` + `agent_handoff.md` |
| **Claude Code** | `npx -y skills add https://github.com/KunChen1110/InterviewRadar -a claude-code -g` |
| **Codex / 其他** | clone 后按 `SKILL.md` 执行即可 |

## 快速开始（Claude Code Skill）

**前置**:已安装 [Claude Code](https://claude.ai/code)。

```bash
# A. 一行安装(需 npm,-g = 全局)
npx -y skills add https://github.com/KunChen1110/InterviewRadar -a claude-code -g

# 或 B. 手动 clone
git clone https://github.com/KunChen1110/InterviewRadar.git ~/.claude/skills/interview-radar

# 装 Python 依赖
cd ~/.claude/skills/interview-radar
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
```

在 Claude Code 里调用:

```
用 interview-radar 跑一下:
简历 /path/to/your-resume.pdf
方向:AI 应用开发岗
```

### Web UI（本地）

```bash
interview-radar-web --port 8765
```

浏览器打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)：填写岗位、粘贴/上传简历，生成题库与 Agent 交接包。

### Codex 使用

Codex 不需要走 Claude Skill 安装器。把仓库 clone 到本地,进入项目目录,安装 Python 依赖即可:

```bash
git clone https://github.com/KunChen1110/InterviewRadar.git
cd InterviewRadar
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
```

在 Codex 里直接说:

```text
按这个项目的 SKILL.md 跑 InterviewRadar:
简历 /path/to/your-resume.pdf
方向:AI 应用开发岗
```

Codex 会读取仓库里的 `SKILL.md`,调用 `scripts/` 下的确定性脚本,并把结果写到 `corpus_cache/prep_package.md`。如果你已经在这个仓库工作区里,不需要额外安装 skill,直接让 Codex 按 `SKILL.md` 执行即可。

Agent 会自动:
1. 读简历(支持文字 PDF + 图片 + 扫描件)
2. 用 WebSearch 发现牛客 / 公开正文页 URL
3. 按域名分桶,调对应 connector 抓取
4. 时效过滤(默认 730 天)+ 频次×时效排序
5. 项目锚定生成追问链
6. 输出中文备考包到 `corpus_cache/prep_package.md`

### 默认数据源

| 源 | 拿到什么 |
|---|---|
| 牛客(NowCoder) | 真实面经帖,带 createTime;自动解析公司/岗位 |
| 小红书(可选) | 通过 MediaCrawler 按关键词搜索;支持图片 OCR deep 模式 |

检索策略以 **`{公司} {岗位} 面经`** 为主,用 `scripts/corpus/classify.py` 生成批次、`group.py` 汇总矩阵。**不再使用** GitHub、知乎、CSDN 等补充源。

牛客零配置;小红书需一次性配置 MediaCrawler(见下方进阶说明)。

<details>
<summary><b>(进阶,可选)接入小红书源</b></summary>

小红书面经笔记很多,但平台反爬严,**不能直接抓**——需要一次性配置 MediaCrawler。配完之后 agent 会通过本项目 connector 自动调用,**不用每次手动跑**。

```bash
# 一、安装 MediaCrawler(默认路径 ~/.mediacrawler)
if [ ! -d "$HOME/.mediacrawler" ]; then
  git clone https://github.com/NanmiCoder/MediaCrawler.git ~/.mediacrawler
fi
cd ~/.mediacrawler

python3.11 -m venv venv || python3 -m venv venv
venv/bin/python -m pip install -U pip
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m playwright install chromium

# 二、复制小红书 web_session 到配置文件
# 打开 ~/.mediacrawler/config/base_config.py,改这几行:
# LOGIN_TYPE = "cookie"
# COOKIES = "web_session=<你从浏览器复制的 web_session 值>"
# ENABLE_CDP_MODE = False
# ENABLE_GET_COMMENTS = False

# 三、验证
venv/bin/python main.py --platform xhs --lt cookie --type search --keywords "AI应用开发 面经" --save_data_option json --get_comment no
```

成功后会生成 `~/.mediacrawler/data/xhs/json/search_contents_*.json`。如果你看到 `zsh: command not found: pip`,不要装全局 pip,用上面的 `venv/bin/python -m pip ...`。

小红书有两种读取深度:

| 模式 | 读取内容 | 适合场景 |
|---|---|---|
| fast | 标题、正文 caption、标签、发布时间 | 快速召回、确认登录和关键词是否跑通 |
| deep | fast 内容 + 按顺序下载图片并 OCR | 正式生成备考包。小红书很多面经正文只放一部分,完整题目在图片里,这种必须用 deep |

所以报告里会标注本次小红书源用的是 `fast` 还是 `deep`。如果只跑了 fast,结论只能代表文字区可见内容,不能当作完整小红书面经覆盖。

完事。Claude Code 或 Codex 接下来要小红书数据时会自动 shell out 调 MediaCrawler。登录过期前不用再管。

详见 [`docs/setup/mediacrawler.md`](docs/setup/mediacrawler.md)。MediaCrawler 仅供个人非商用。

</details>

## 它怎么工作

<div align="center">
  <img src="assets/workflow.png" alt="InterviewRadar workflow" width="900"/>
</div>

<details>
<summary>等价的 Mermaid 流程图(技术细节)</summary>

```mermaid
flowchart TD
    R["简历 PDF / 图片"] --> A
    D["模糊岗位方向"] --> A
    A["Agent (Claude Code / Codex)"] --> S1["Step 1<br/>简历理解<br/>pypdf + 视觉回退"]
    S1 --> S2["Step 2<br/>种子查询<br/>agent 当场推,不依赖预设词表"]
    S2 --> S3a["Step 3a<br/>WebSearch 发现 URL<br/>按域名分桶"]
    S3a --> S3b["Step 3b: dispatch connector"]
    S3b --> C1["NowCoder<br/>(官方 discuss)"]
    S3b --> C2["Xiaohongshu<br/>(via MediaCrawler)"]
    C1 --> S45["Step 4-5<br/>内容相关性 + 题目抽取<br/>文本 / OCR / 视觉"]
    C2 --> S45
    S45 --> S6["Step 6<br/>时效过滤 730d 硬截断<br/>频次 × 时效排序<br/>公司×岗位分类"]
    S6 --> S7["Step 7<br/>项目锚定推理<br/>高频题 ↔ 简历项目"]
    S7 --> OUT["prep_package.md (中文)"]

    classDef in fill:#fff3cd,stroke:#856404
    classDef stage fill:#d1ecf1,stroke:#0c5460
    classDef src fill:#d4edda,stroke:#155724
    classDef out fill:#f8d7da,stroke:#721c24
    class R,D in
    class S1,S2,S3a,S3b,S45,S6,S7 stage
    class C1,C2 src
    class OUT out
```

</details>

## 分工原则

- **Python**:采集、OCR、粗抽题、排序、`question_bank.json`、`agent_handoff.md`
- **Agent**:步骤 4–8 — 相关性、题目精炼、项目锚定、**`prep_package.md`**
- agent(Claude Code / Codex)做**推理判断**;Python 做**确定性脏活**
- 两者通过磁盘 JSON 解耦,可独立调试

## 它的差异化

| | 静态题库(JavaGuide / Xiaolincoding / GitHub repo) | LLM 直接出题 | **InterviewRadar** |
|---|---|---|---|
| 时效 | ❌ 经常陈旧 | ⚠️ 不可控 | ✅ 730d 硬过滤 |
| 个性化 | ❌ 不看你简历 | ⚠️ 听起来像但不溯源 | ✅ 项目锚定 + `is_grounded` 标记 |
| 可追溯 | ✅ 但散落 | ❌ 编的就是编的 | ✅ 每条题 / 追问都带源链接 |
| 公司×岗位分类 | ❌ | ❌ | ✅ 检索与输出按 taxonomy 组织 |
| 跨领域 | ❌ 一仓一岗 | ✅ | ✅(不依赖预设词表) |
| 多源 | ❌ 单一 | ❌ 不爬 | ✅ 牛客 + 小红书(可选) |

## 项目结构

```
InterviewRadar/
├── pyproject.toml               ← pip install -e . 与 CLI 入口
├── examples/
│   ├── sample_raw_posts.json    ← 离线 demo 语料（可提交）
│   ├── sample_resume.txt
│   └── sample_prep_package.md
├── SKILL.md                     ← Claude Code / Codex 的入口工作流
├── scripts/
│   ├── run.py                   ← CLI: interview-radar
│   ├── doctor.py                ← 环境检查: interview-radar-doctor
│   ├── agent_handoff.py         Agent 交接包（步骤 4–8）
│   ├── api/server.py            ← Web: interview-radar-web
│   ├── connectors/              source connectors:
│   │   ├── nowcoder.py            ├─ 牛客 (选择器漂移守卫 + anti-bot 半空守卫)
│   │   └── xiaohongshu.py         └─ 小红书 (吃 MediaCrawler 导出)
│   ├── corpus/
│   │   ├── classify.py          公司/岗位解析 + 检索词批次
│   │   ├── group.py             公司×岗位汇总矩阵
│   │   ├── store.py             RawPost / Question 存取
│   │   ├── recency.py           时效过滤(730d)
│   │   └── dedupe_rank.py       去重 + 频次×时效排序(未标日期降权 0.2)
│   ├── ocr/
│   │   ├── extract.py           OCR + 视觉回退
│   │   └── xhs_images.py        小红书图片下载 + OCR 拼接
│   └── scrape/normalize_xhs.py  MediaCrawler 输出适配器
├── tests/                       单测(TDD)
├── config/
│   └── company_aliases.yaml     公司名归一化（子公司→主公司，可 PR）
├── docs/
│   ├── GETTING_STARTED.md       开源上手指南
│   ├── CORPUS_SYNC.md           语料目录、多岗位、增量、fork 同步
│   ├── specs/                   设计文档
│   ├── plans/                   实施计划
│   └── setup/mediacrawler.md    小红书源接入
├── examples/                    可提交的 demo 输入/样例输出
└── corpus_cache/                运行时产物（gitignored，勿提交）
```

## 开发

```bash
make install-dev   # 或 pip install -e ".[dev]"
make test
make demo          # 离线 demo
interview-radar-doctor
```

**怎么加新源**:实现 `Connector` ABC(见 `scripts/connectors/base.py`),返回 `SearchResult`。降级时用 `SearchResult.degraded(name, msg)`,绝不抛异常打断管道。

**怎么调整时效窗口 / 排序权重**:见 `scripts/corpus/recency.py` 和 `scripts/corpus/dedupe_rank.py`,纯函数,容易改 + 测试覆盖好。

**面经语料 / 多岗位建库 / 增量抓取 / Fork 数据同步**:见 [docs/CORPUS_SYNC.md](docs/CORPUS_SYNC.md)（`full_scrape`、`daily_scrape --role-ids`、`config/company_aliases.yaml`）。

**怎么扩展公司名归一化**:编辑 [`config/company_aliases.yaml`](config/company_aliases.yaml)（子公司→主公司、禁止当公司名的词），重建 bank 生效；也可用 `COMPANY_ALIASES_PATH` 指向自定义文件。

## Roadmap

- [x] **小红书 live 采集**:MediaCrawler cookie driver 已接入,支持按关键词自动抓取小红书 notes JSON,并进入 `XiaohongshuConnector`。
- [x] **小红书基础适配**:MediaCrawler 原生 JSON 已能 normalize 成 `RawPost`,支持标题、正文、时间戳、图片 URL。
- [x] **Plan 7:小红书图片面经补全**:`image_list` 会按顺序下载到 `corpus_cache/assets/xhs/{note_id}/`,优先用图片 OCR 作为 `RawPost.raw_text/content_text` 主正文;标题、caption、tags 只进入 `locator_text`,并保留低置信度 vision fallback。
- [x] **Plan 8:`extract_questions()` 自动抽题**: `scripts/corpus/extract_questions.py` + `scripts/run.py` 统一入口。
- [x] **Plan 9:端到端 runner + HTTP API**: `scripts/run.py` + `scripts/service.py` + `scripts/api/server.py`(`/api/bank`, `/api/predict`);牛客 URL 自动发现 `--discover-nowcoder`。
- [ ] **Plan 10:抖音图文/视频源 MVP**:优先通过 MediaCrawler 接入抖音图文、标题、描述、评论文本;视频 ASR 先做接口与降级提示,确认高密度面经后再接完整转写。
- [ ] **持久化术语词典**:跨 session 累积岗位名、公司名、技术词和真实高频术语,用于下一轮查询扩展。
- [ ] **评测体系**:Golden Set + Trace 回放,覆盖 OCR 抽题、自动抽题、排序和备考包生成质量。

## 贡献

欢迎 issue / PR。请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)。开发流程: `docs/specs/` → `docs/plans/` → TDD → review。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=KunChen1110/InterviewRadar&type=Date)](https://www.star-history.com/#KunChen1110/InterviewRadar&Date)

## 免责

仅供个人非商用。使用本工具拉取数据的合规性由用户自担。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

MIT © 2026 Kun Chen
