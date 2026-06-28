# InterviewRadar — 项目规则

## 项目目标

抓取小红书和牛客上**数据开发**与**Agent开发**两个岗位近三个月的面经，生成高质量题库，并获取互联网大厂的在招岗位信息。

### 功能模块

1. **面经抓取**
   - 数据源：小红书（主）、牛客（辅）
   - 岗位范围：数据开发（数仓/ETL/Spark/Flink）+ Agent开发（RAG/Agent/MCP/LLM应用）
   - 时间窗口：近三个月
   - 公司标签：只保留大厂（字节、腾讯、阿里、美团、京东、百度、快手、网易、滴滴、小红书、bilibili、拼多多、OPPO、vivo、华为、小米等），其余归入「其他」
   - 图片帖处理：下载图片 → RapidOCR 读取文字 → 合并入正文
   - 支持增量抓取（不重复抓已有内容）

2. **题库生成**
   - 从面经中提取面试题目
   - 按**出现频次**降序排列
   - 按**考察方向**分类（Spark/计算、Hive/SQL、数仓建模、Flink/实时、数据工程、RAG、Agent、MCP/协议、LLM基础、手撕代码、项目深挖、后端八股、产品/业务、综合）
   - AI语义去重合并相似题目

3. **岗位信息**
   - 数据源：互联网大厂招聘官网 + Boss直聘
   - 支持增量抓取

---

## 核心原则（必须遵守）

### 原则一：AI First
- **能调用 AI（DeepSeek API）解决的问题，不写程序逻辑**
- 面经内容筛选（是否为真实面经、是否属于目标岗位）→ 用 `judge_post()` DeepSeek 判断
- 题目去重/分类/质量过滤 → 用 `cluster_questions()` DeepSeek 聚类
- 公司名称识别、岗位识别 → 优先 AI，regex 只作兜底
- 规则/正则只作 AI 不可用时的离线 fallback，**不作主要逻辑**

### 原则二：复用开源库，不造轮子
- 文本相似度 → **rapidfuzz**（`token_set_ratio`），不自己实现 Jaccard
- OCR → **RapidOCR**，不自己调 Tesseract 或写 CV 逻辑
- 爬虫 → 复用 **Spider_XHS**（小红书）、**MediaCrawler** 作备选
- HTML 解析 → **BeautifulSoup**，不手写 regex 解析 HTML
- 遇到新需求先找开源库，找不到再自己实现

---

## 当前已知痛点

1. **面经抓取**
   - 小红书反爬：需 Cookie（`web_session`）+ Spider_XHS CDP 模式
   - 帖子内容不完整：牛客帖需二次请求详情页（`enrich_nowcoder_text()`）
   - 图片帖 OCR 质量差：RapidOCR 对低分辨率/竖排文字效果有限，需 `needs_vision_fallback` 标记

2. **面经筛选**
   - 广告/求助帖混入 → DeepSeek `judge_post()` 主过滤，`ai_enabled()` 需配置 `DEEPSEEK_API_KEY`
   - 其他岗位面经污染 → `judge_post()` 返回 `role_id` 字段过滤非目标岗位
   - 离线 fallback（无 API key 时）精度有限

3. **题库质量**
   - 排序：已修复为按 `batch_count`（频次）降序
   - 自我介绍/感慨等非题内容 → `filter_questions()` 前置清洗（已修复为始终执行）
   - 后端 C++/Java 题混入数据开发题库 → `cluster_questions()` AI 提示词已增加角色意识

---

## 环境配置

```
DEEPSEEK_API_KEY=<your-key>       # 必填，AI过滤/聚类/生成答案
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
XHS_WEB_SESSION=<cookie-value>    # 小红书抓取
```

配置写入项目根目录 `.env` 文件，`bootstrap_env()` 自动加载。
