# InterviewRadar · AI 升级路线图

> 沿「数据质量 → 个性化 → 交互 → 闭环」递进，不推倒重来，在现有骨架上叠加。

---

## 现状速览

| 已有能力 | 缺口 |
|----------|------|
| 帖子 keep/drop（规则 + DeepSeek `judge_post`） | `judge_post` 与 `post_ai_filter` 两套并存，未统一 |
| 题目聚类 + Top40 参考答案 | 个性化仍是 token 重叠，非语义推理 |
| OCR 低质量标记（`needs_vision_fallback`） | Vision 补读只写在 handoff，未自动闭环 |
| 导出 `prep_package` 给外部 Agent | 用户需自己接 Cursor/Claude，门槛高 |
| 按频次排序题库 | 无 embedding 检索，缺「这道题和我多相关」 |

---

## 方向一：补齐「已设计但未闭环」的能力（优先级最高）

### 1. Vision 补读自动化

**背景**：代码里已大量标记 `needs_vision_fallback`，`agent_handoff` 要求「不得猜测」，但仍依赖人工触发外部 Agent。

**升级方案**：
- 对 OCR 失败 / 低置信度图片，自动调用多模态模型（DeepSeek-VL / Qwen-VL / GPT-4o）
- 输出结构化字段：`questions[]`、`company`、`round`、`extraction_confidence`
- 写回 `RawPost`，标记 `modality_origin: vision`

**相关文件**：`scripts/ocr/post_images.py`、`scripts/models.py`（`needs_vision_fallback`）

**价值**：小红书图片面经是当前最大数据痛点，ROI 最高的单点升级。

---

### 2. 把 `agent_handoff` 内化成「Prep Agent」

**背景**：`agent_handoff.py` 已定义步骤 4–8（相关性复核、题目 refinement、项目锚定追问、生成 `prep_package`），目前是导出 JSON 给外部。

**升级方案**：
- 用 DeepSeek 在服务端自动执行步骤 4–8
- Web UI 一键生成完整备考包，不再需要「下载 handoff 自己喂 Agent」
- 保留三档模式：`prep_mode=agent|auto|heuristic`

**相关文件**：`scripts/corpus/agent_handoff.py`、`scripts/api/server.py`

**价值**：产品从「工具 + 半成品」升级为「端到端 AI 产品」。

---

## 方向二：从「频次排序」到「语义理解」

### 3. 本地语料 RAG

**背景**：`corpus_cache/` 已有大量帖子、题目、解答，但没有向量检索。`Question.source_refs`、`RawPost.url` 天然适合做 citation。

**升级方案**：
```
面经帖/题目 → embedding → 本地向量库（Chroma / sqlite-vec）
       ↓
用户问：「字节数据开发三面 Spark 常考什么？」
       ↓
检索相关帖 + 题目簇 → LLM 综合回答（带 source_refs）
```

**典型场景**：
- 「和我简历相关的 Top 20 题」——简历 embedding 做 query
- 「某公司最近一个月新增考点」——时间 + 公司 metadata 过滤
- 「这道题在哪些面经里出现过」——可追溯引用

**相关文件**：`scripts/corpus/dedupe_rank.py`、`scripts/models.py`（`Question.source_refs`）

---

### 4. AI 驱动的「考点趋势」分析

**背景**：现在排序靠 `batch_count`（频次），缺「新出现 / 升温」信号——「面试雷达」名字还没真正体现。

**升级方案**：
- 按周/月对题目 embedding 聚类，识别新兴考点
- LLM 生成趋势报告：「近 4 周 Agent 岗 MCP 相关题 +40%」「某厂手撕题从 DP 转向图论」
- Web UI 增加趋势仪表盘

**相关文件**：`scripts/jobs/tech_stack.py`（现有技术栈分析可扩展）、`scripts/api/server.py`

---

## 方向三：个性化深度升级

### 5. 简历 → 追问链（替换启发式匹配）

**背景**：`personalize.py` 明确注释 `heuristic preview only`，`score_resume_match` 是 token 重叠，非语义推理。

**升级方案**：
- 输入：简历结构化摘要 + 高频题 Top N
- LLM 输出 `FollowUpChain`：

```python
{
  "anchor_project": "电商知识库项目",        # 简历里的锚点
  "trigger_question": "RAG 召回不准怎么优化？",  # 面经原题
  "followups": [
    "你们 chunk 策略是什么？",
    "rerank 用的什么模型？",
    "线上 badcase 怎么归因？"
  ],
  "is_grounded": true   # 是否有 source_refs 支撑
}
```

- 与 `agent_handoff` 第 7 步对齐，但内置自动执行

**相关文件**：`scripts/corpus/agent_handoff.py`（步骤 7）

---

### 6. JD ↔ 面经联动分析

**背景**：`scripts/jobs/interview_link.py` 已存在基础骨架。

**升级方案**：
- 输入：目标岗位 JD + 该公司面经库
- 输出：JD 技能点覆盖度 + 缺口题单 + 建议准备优先级
- 示例：JD 强调 Flink，但题库 Flink 频次低 → 主动补抓 + 生成专项练习

**相关文件**：`scripts/jobs/interview_link.py`、`scripts/jobs/tech_stack.py`

---

## 方向四：交互形态升级

### 7. 模拟面试 Agent（对话式）

**升级方案**：在现有题库 + 参考答案之上加一层多轮对话

| 模式 | 行为 |
|------|------|
| 技术面 | 抽题 → 用户作答 → AI 点评 + 追问 |
| 项目深挖 | 基于简历项目连续拷打 |
| 手撕代码 | 出题 → 看思路 → 提示 → 标准解 |

**轻量实现路径**：
- 状态机 + 题库抽样 + DeepSeek 作面试官
- 每次对话记录 `weak_topics`，反哺个性化排序

---

### 8. 错题本 / 掌握度学习闭环

**升级方案**：
- 用户对每题标记：不会 / 模糊 / 掌握
- AI 根据标记 + 面试日期生成每日复习计划
- 考前 3 天自动压缩到「必背 Top 15」

**价值**：从「生成工具」到「学习产品」的关键一步。

---

## 方向五：工程与成本优化

### 9. 统一 AI Gateway

**背景**：`ai_gate.chat_json` 与 `post_ai_filter.deepseek_classify_post` 重复实现，缺统一缓存和成本统计。

**升级方案**：

```python
# scripts/ai/gateway.py
class AIGateway:
    def chat_json(system, user, *, model, cache_key=None) -> dict
    def embed(texts: list[str]) -> list[vector]
    def vision_extract(image_path, schema) -> dict
```

附带：
- 统一缓存（帖子/题目/解答/embedding）
- 模型路由：便宜模型做过滤，强模型做 `prep_package`
- 成本统计：每次 pipeline 花了多少 token

**相关文件**：`scripts/corpus/ai_gate.py`、`scripts/corpus/post_ai_filter.py`（待合并）

---

### 10. 评估与反馈飞轮

**背景**：没有 eval，AI 升级容易「感觉变好、实际变差」。

**升级方案**：
- 建立题目提取/过滤的黄金标注集（100 条）
- 每次 pipeline 变更跑 eval，输出 precision/recall
- 用户「标记错误」反馈写回训练数据

---

## 优先级总览

| 优先级 | 方向 | 预估收益 | 依赖 |
|--------|------|----------|------|
| 🔴 P0 | Vision 补读自动化（#1） | 解锁图片面经，数据量 +50% | 多模态 API |
| 🔴 P0 | Prep Agent 内化（#2） | 产品完整闭环 | 现有 DeepSeek |
| 🟠 P1 | AI Gateway 统一（#9） | 支撑所有后续 AI 升级 | 无 |
| 🟠 P1 | 本地语料 RAG（#3） | 语义检索，个性化基础 | embedding 模型 |
| 🟡 P2 | 简历追问链（#5） | 高价值个性化 | RAG（#3）+ DeepSeek |
| 🟡 P2 | JD ↔ 面经联动（#6） | 备考针对性 | 现有 jobs 模块 |
| 🟡 P2 | 考点趋势分析（#4） | 「雷达」定位实现 | embedding（#3）|
| 🟢 P3 | 模拟面试 Agent（#7） | 交互跃升 | Prep Agent（#2）|
| 🟢 P3 | 错题本闭环（#8） | 学习产品化 | Web UI 改造 |
| 🟢 P3 | 评估飞轮（#10） | 质量保障 | 标注数据 |
