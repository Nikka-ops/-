<div align="center">

# InterviewRadar · 面试雷达

**自动抓取小红书 & 牛客真实面经 → AI 过滤 → 生成高频题库 + 在招岗位信息**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](#)
[![DeepSeek](https://img.shields.io/badge/AI-DeepSeek-blue.svg)](#)

</div>

---

## 它解决什么问题

求职时你需要的是**最近三个月、跟你目标岗位直接相关、高频出现**的面试题——而不是某个静态题库。

InterviewRadar 自动帮你：

| 输入 | 处理 | 输出 |
|------|------|------|
| 小红书 / 牛客面经帖 | DeepSeek AI 过滤垃圾帖、OCR 读图片、提取题目 | 按频次排序的题库 |
| 岗位 + 公司筛选 | 近 90 天时效过滤、公司标签归一化 | 高频题参考解答 |
| Boss 直聘 / 大厂官网 | 增量抓取，去重 | 在招岗位 JD |

---

## 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/Nikka-ops/-.git interview-radar
cd interview-radar
bash install.sh
```

或手动：

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# 必填 — AI 过滤 / 题目聚类 / 生成解答
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 小红书抓取（可选）
XHS_WEB_SESSION=<从浏览器 DevTools 复制 web_session 值>
```

### 3. 启动 Web UI

```bash
bash start-web.sh
# 或
.venv/bin/python -m scripts.api.server --port 8099
```

浏览器打开 [http://localhost:8099](http://localhost:8099)

---

## 核心功能

### 面经抓取

- **小红书**：通过 [Spider_XHS](docs/setup/spider_xhs.md) CDP 模式抓取，支持增量（不重复抓已有内容）
- **牛客**：自动发现面经帖，二次请求详情页获取完整正文
- **图片帖**：自动下载图片 → RapidOCR 读取文字 → 合并入正文

### AI 过滤（需配置 DeepSeek API Key）

每条面经经过 DeepSeek `judge_post()` 判断：
- `keep=false`：广告、求助、培训、外贸、其他岗位
- `role_id`：识别是数据开发还是 Agent 开发，过滤不相关岗位
- 无 API Key 时自动降级为正则 fallback

### 题库生成

- 按**出现频次**降序排列（高频 ≥3 次、中频 2 次、低频 1 次）
- 按考察方向自动分类：Spark/计算、Hive/SQL、数仓建模、Flink/实时、RAG、Agent、MCP/协议、LLM基础、手撕代码等
- DeepSeek 语义去重合并相似题目
- Top 40 题自动生成参考解答

### 在招岗位

```bash
.venv/bin/python -m scripts.run_jobs --role-id data --companies 字节跳动 阿里巴巴
```

支持 Boss 直聘（需配置 `BOSS_ZHIPIN_COOKIE`）和大厂招聘官网。

---

## 支持的岗位

| 岗位 | role_id | 关键技术方向 |
|------|---------|-------------|
| 数据开发 | `data` | Spark / Flink / Hive / 数仓 / ETL |
| AI 应用开发 | `ai_app` | RAG / Agent / MCP / LLM 应用 |

目标公司：字节跳动、腾讯、阿里巴巴、美团、京东、百度、快手、网易、滴滴、小红书、bilibili、拼多多、OPPO、vivo、华为、小米等大厂，其余归入「其他」。

---

## 项目结构

```
interview-radar/
├── .env                         ← 配置（不提交）
├── CLAUDE.md                    ← 项目规则（AI 开发原则）
├── scripts/
│   ├── api/
│   │   ├── server.py            ← Web UI 后端
│   │   └── static/              ← 前端（app.js / style.css）
│   ├── corpus/
│   │   ├── ai_gate.py           ← DeepSeek 调用（过滤/聚类/解答）
│   │   ├── post_filter.py       ← AI + 离线双重过滤
│   │   ├── extract_questions.py ← 从面经正文提取题目
│   │   ├── quality.py           ← 题目基础质量过滤
│   │   ├── pipeline.py          ← 题库生成流水线
│   │   ├── dedupe_rank.py       ← 去重 + 频次×时效排序
│   │   └── semantic_merge.py    ← rapidfuzz 语义去重
│   ├── ocr/
│   │   ├── xhs_images.py        ← RapidOCR 图片识别
│   │   └── post_images.py       ← 图片下载 + OCR pipeline
│   ├── scrape/
│   │   └── spider_xhs_driver.py ← Spider_XHS CDP 驱动
│   ├── service.py               ← 主流水线入口
│   └── models.py                ← RawPost / Question 数据模型
├── corpus_cache/                ← 运行时数据（gitignored）
│   ├── banks/                   ← 题库缓存
│   ├── assets/                  ← 下载的图片
│   └── ocr/                     ← OCR 缓存
└── config/
    └── company_aliases.yaml     ← 公司名归一化配置
```

---

## 开发原则

1. **AI First**：能用 DeepSeek API 解决的问题不写程序逻辑，正则只作离线 fallback
2. **复用开源库**：OCR → RapidOCR，相似度 → rapidfuzz，爬虫 → Spider_XHS
3. **增量优先**：面经和岗位信息均支持增量抓取，不重复处理已有数据

---

## 小红书接入（可选）

小红书需要一次性配置 Spider_XHS：

```bash
# 安装 Spider_XHS
pip install spider-xhs

# 在 .env 中配置 Cookie
XHS_WEB_SESSION=<从浏览器 DevTools Application → Cookies 复制>
```

详见 [docs/setup/spider_xhs.md](docs/setup/spider_xhs.md)

---

## 已知限制

- 小红书反爬严格，Cookie 需定期更新（约 1-2 周）
- 图片帖 OCR 对低分辨率/竖排文字识别率有限，低质量图自动标记 `needs_vision_fallback`
- 无 DeepSeek API Key 时过滤精度有限（离线正则 fallback）

---

## License

MIT © 2026
