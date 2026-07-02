"""Prep Agent — 服务端自动执行 agent_handoff 步骤 4–8。

模式：
    prep_mode=auto    → 服务端全自动（本文件）
    prep_mode=agent   → 导出 handoff JSON 给外部 Agent（原有逻辑）
    prep_mode=heuristic → 纯本地启发式（无 API Key 时 fallback）

输出：PrepPackage，包含：
    - followup_chains : 追问链列表（基于简历 + 面经题）
    - refined_questions: AI 精炼后的题目列表
    - prep_md          : 可直接阅读的 Markdown 备考包
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.models import FollowUpChain, Question


# --------------------------------------------------------------------------- #
#  Prompts                                                                     #
# --------------------------------------------------------------------------- #
_FOLLOWUP_SYS = """你是一位资深技术面试教练，熟悉数据开发/Agent 岗位。
根据候选人简历和高频面试题，生成「追问链」：
- anchor_project: 简历中最相关的项目/技能（不超过 20 字）
- trigger_question: 与面试题最契合的原题
- followups: 面试官可能追问的 2~3 个深度问题（体现技术纵深）
- is_grounded: 追问是否有简历项目支撑（true/false）

JSON 格式：
{"chains":[{"anchor_project":"","trigger_question":"","followups":[""],"is_grounded":true}]}
每组 trigger_question 来自输入的 top_questions，最多生成 8 条追问链。"""

_REFINE_SYS = """你是面经题目精编助手。对输入题目列表做：
1. 去掉非问句、自我介绍、寒暄等非题内容
2. 补全语义不完整的题目（如「讲一下 Spark」→「请描述 Spark 的 RDD 执行原理」）
3. 按考察方向分组，每组内按重要性排序
4. 不新增题目，只整理原有题目

JSON: {"refined":[{"id":"原id","text":"精编后题目","topic":"考察方向"}]}"""

_PREP_PACKAGE_SYS = """你是备考文档撰写专家。
根据提供的「目标岗位 + 公司 + 追问链 + 高频题库」，撰写一份 Markdown 格式备考包：
- 结构：概述 → 高频考点（按 topic 分组）→ 项目追问准备 → 临考建议
- 每道题配简要答题要点（3~5 条）
- 总字数 800~1500 字，不要废话"""


# --------------------------------------------------------------------------- #
#  数据类                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class PrepPackage:
    role: str
    companies: list[str]
    followup_chains: list[FollowUpChain] = field(default_factory=list)
    refined_questions: list[dict] = field(default_factory=list)
    prep_md: str = ""
    mode: str = "auto"
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["followup_chains"] = [asdict(c) for c in self.followup_chains]
        return d


# --------------------------------------------------------------------------- #
#  追问链生成                                                                   #
# --------------------------------------------------------------------------- #
def generate_followup_chains(
    top_questions: list[Question],
    resume_text: str,
    role: str,
    *,
    max_chains: int = 8,
) -> list[FollowUpChain]:
    from scripts.ai.gateway import chat_json

    if not resume_text.strip():
        return []

    q_list = [{"id": getattr(q, "id", None) or q.cluster_id or str(i), "text": q.text, "topic": q.topic or ""} for i, q in enumerate(top_questions[:20])]
    user = json.dumps({
        "role": role,
        "resume_summary": resume_text[:600],
        "top_questions": q_list,
        "max_chains": max_chains,
    }, ensure_ascii=False)

    result = chat_json(_FOLLOWUP_SYS, user, task="prep")
    if not result:
        return []

    chains: list[FollowUpChain] = []
    for item in result.get("chains") or []:
        try:
            chains.append(FollowUpChain(
                seed_question=str(item.get("trigger_question") or ""),
                resume_anchor=str(item.get("anchor_project") or ""),
                followups=[str(f) for f in (item.get("followups") or [])],
                is_grounded=bool(item.get("is_grounded", False)),
            ))
        except Exception:  # noqa: BLE001
            continue
    return chains


# --------------------------------------------------------------------------- #
#  题目精炼                                                                     #
# --------------------------------------------------------------------------- #
def refine_questions(
    questions: list[Question],
) -> list[dict]:
    from scripts.ai.gateway import chat_json

    if not questions:
        return []

    q_list = [{"id": getattr(q, "id", None) or q.cluster_id or str(i), "text": q.text} for i, q in enumerate(questions[:60])]
    user = json.dumps({"questions": q_list}, ensure_ascii=False)
    result = chat_json(_REFINE_SYS, user, task="cluster")
    if not result:
        return [{"id": getattr(q, "id", None) or q.cluster_id or str(i), "text": q.text, "topic": q.topic or ""} for i, q in enumerate(questions)]

    return result.get("refined") or []


# --------------------------------------------------------------------------- #
#  Markdown 备考包生成                                                          #
# --------------------------------------------------------------------------- #
def generate_prep_md(
    role: str,
    companies: list[str],
    top_questions: list[Question],
    followup_chains: list[FollowUpChain],
) -> str:
    from scripts.ai.gateway import chat_json

    q_grouped: dict[str, list[str]] = {}
    for q in top_questions[:40]:
        topic = q.topic or "综合"
        q_grouped.setdefault(topic, []).append(q.text)

    chains_data = [
        {
            "anchor": c.resume_anchor,
            "question": c.seed_question,
            "followups": c.followups,
        }
        for c in followup_chains[:5]
    ]

    user = json.dumps({
        "role": role,
        "companies": companies,
        "question_groups": q_grouped,
        "followup_chains": chains_data,
    }, ensure_ascii=False)

    result_raw = chat_json(_PREP_PACKAGE_SYS, user, task="prep")
    # prep_package 让 AI 直接返回 Markdown 文本
    # 由于 response_format=json_object，包装一层
    if result_raw and result_raw.get("markdown"):
        return str(result_raw["markdown"])
    if result_raw and result_raw.get("content"):
        return str(result_raw["content"])

    # fallback：拼接结构化内容
    lines = [f"# {role} 备考包\n"]
    if companies:
        lines.append(f"**目标公司**：{', '.join(companies)}\n")
    lines.append("## 高频考点\n")
    for topic, qs in q_grouped.items():
        lines.append(f"### {topic}")
        for q in qs[:5]:
            lines.append(f"- {q}")
        lines.append("")
    if followup_chains:
        lines.append("## 项目追问准备\n")
        for c in followup_chains[:4]:
            lines.append(f"**{c.resume_anchor}** × *{c.seed_question}*")
            for f in c.followups:
                lines.append(f"  - {f}")
            lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  主入口                                                                       #
# --------------------------------------------------------------------------- #
def build_prep_package(
    *,
    role: str,
    companies: list[str],
    top_questions: list[Question],
    resume_text: str = "",
    mode: str = "auto",
) -> PrepPackage:
    """
    自动执行 prep 步骤 4–8，返回 PrepPackage。

    mode:
        auto      → AI 全流程（需 API Key）
        heuristic → 本地 fallback（无 AI）
    """
    from scripts.ai.gateway import chat_json as _gw

    pkg = PrepPackage(role=role, companies=companies, mode=mode)

    if mode == "heuristic" or not _gw:
        # 本地 fallback：不调 AI，只整理题目
        pkg.refined_questions = [{"id": getattr(q, "id", None) or q.cluster_id or str(i), "text": q.text, "topic": q.topic or ""} for i, q in enumerate(top_questions)]
        return pkg

    # Step 5b: 题目精炼
    pkg.refined_questions = refine_questions(top_questions)

    # Step 7: 追问链（需要简历）
    if resume_text.strip():
        pkg.followup_chains = generate_followup_chains(
            top_questions, resume_text, role
        )

    # Step 8: 生成备考 Markdown
    pkg.prep_md = generate_prep_md(role, companies, top_questions, pkg.followup_chains)

    from scripts.ai.gateway import get_stats
    pkg.stats = get_stats()

    return pkg
