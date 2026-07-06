"""JD ↔ 面经联动分析。

输入：JD 正文 + 题库题目列表
输出：
  - jd_skills: JD 要求的技能点列表
  - coverage: 每个技能点在题库中的覆盖度 (0~1)
  - gaps: 覆盖不足的技能点（建议重点备考）
  - priority_questions: 与 JD 最相关的题目列表
  - summary: AI 生成的备考建议
"""
from __future__ import annotations

import json

_JD_ANALYSIS_SYS = """你是技术岗位备考顾问。
根据岗位 JD 和现有面经题库，输出结构化分析：
1. 提取 JD 明确要求的技能点（skill_points，每项 ≤10 字）
2. 对每个技能点，从题库中找最相关的题目（relevant_questions，最多 3 条题目 id）
3. 给每个技能点评估题库覆盖度（coverage：0=无题/0.5=少量/1=充分）
4. 指出覆盖不足的技能点作为备考缺口（gaps，coverage < 0.5）
5. 写一段 200 字以内的备考建议（recommendation）

JSON 格式：
{
  "skill_points": [
    {"skill": "Flink 实时计算", "coverage": 0.8, "relevant_qids": ["q1","q2"]}
  ],
  "gaps": ["技能点A", "技能点B"],
  "recommendation": "..."
}"""


def analyze_jd_coverage(
    jd_text: str,
    questions: list[dict],
    *,
    max_questions: int = 60,
) -> dict | None:
    """分析 JD 与题库的覆盖情况。questions 为 dict 列表，含 cluster_id/text/topic。"""
    from scripts.ai.gateway import chat_json

    if not jd_text.strip() or not questions:
        return None

    q_sample = [
        {"id": q.get("cluster_id") or q.get("id") or str(i), "text": q.get("text") or "", "topic": q.get("topic") or ""}
        for i, q in enumerate(questions[:max_questions])
    ]

    user = json.dumps({
        "jd": jd_text[:1500],
        "question_bank_sample": q_sample,
    }, ensure_ascii=False)

    return chat_json(_JD_ANALYSIS_SYS, user, task="prep")
