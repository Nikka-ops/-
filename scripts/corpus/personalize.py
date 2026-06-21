"""Resume-aware question ranking — heuristic preview only (not Agent prep package)."""
from __future__ import annotations

import re
from datetime import date

from scripts.corpus.dedupe_rank import normalize
from scripts.models import FollowUpChain, Question

_TOKEN = re.compile(r"[\w一-鿿]{2,}")
_PROJECT_LINE = re.compile(r"(?:项目|实习|经历|负责|开发)[:：]?\s*(.+)", re.I)
_SKILL_LINE = re.compile(r"(?:技能|技术栈|熟悉|掌握)[:：]?\s*(.+)", re.I)

_ROLE_TOPIC_HINTS: dict[str, list[str]] = {
    "AI 应用开发": ["rag", "agent", "mcp", "langchain", "embedding", "prompt", "大模型"],
    "Agent": ["agent", "react", "tool", "mcp", "function", "memory"],
    "数据开发": ["sql", "spark", "hive", "etl", "数仓", "flink"],
    "后端": ["redis", "mysql", "spring", "并发", "tcp", "jvm"],
    "算法": ["transformer", "loss", "训练", "attention", "lora"],
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text)}


def resume_anchors(resume_text: str) -> list[str]:
    anchors: list[str] = []
    for line in resume_text.splitlines():
        for pattern in (_PROJECT_LINE, _SKILL_LINE):
            m = pattern.search(line)
            if m:
                anchors.append(m.group(1).strip()[:120])
        if line.strip().startswith(("P", "项目")) and len(line.strip()) > 4:
            anchors.append(line.strip()[:120])
    if not anchors and resume_text.strip():
        anchors.append(resume_text.strip()[:200])
    return anchors[:5]


def score_resume_match(question: Question, resume_text: str, role: str = "") -> float:
    q_tokens = _tokens(question.text)
    r_tokens = _tokens(resume_text)
    if not q_tokens or not r_tokens:
        return 0.0
    overlap = len(q_tokens & r_tokens) / max(len(q_tokens), 1)
    role_hints = []
    for key, hints in _ROLE_TOPIC_HINTS.items():
        if key.lower() in role.lower() or role.lower() in key.lower():
            role_hints.extend(hints)
    if role_hints:
        hint_hits = sum(1 for h in role_hints if h in normalize(question.text))
        overlap += min(hint_hits * 0.15, 0.45)
    topic_bonus = 0.0
    if question.topic in {"RAG", "Agent", "MCP/协议"} and any(
        h in normalize(resume_text) for h in ("rag", "agent", "langchain", "mcp")
    ):
        topic_bonus = 0.2
    return round(min(overlap + topic_bonus, 1.0), 3)


def predict_questions(
    ranked: list[Question],
    resume_text: str,
    *,
    role: str = "",
    top_n: int = 20,
) -> list[dict]:
    max_freq = max((q.freq for q in ranked), default=1) or 1
    scored: list[tuple[Question, float, float, float]] = []
    for q in ranked:
        resume_match = score_resume_match(q, resume_text, role=role)
        freq_norm = q.freq / max_freq
        combined = round(0.55 * freq_norm + 0.45 * resume_match, 3)
        scored.append((q, resume_match, freq_norm, combined))
    scored.sort(key=lambda x: (-x[3], -x[0].freq))
    out = []
    for q, resume_match, freq_norm, combined in scored[:top_n]:
        out.append(
            {
                "text": q.text,
                "resume_match": resume_match,
                "freq_norm": round(freq_norm, 3),
                "combined_score": combined,
                "freq": q.freq,
                "topic": q.topic,
                "company_tags": q.company_tags,
                "role_tags": q.role_tags,
                "source_refs": q.source_refs,
                "why": _why_predicted(q, resume_match, resume_text),
            }
        )
    return out


def _why_predicted(q: Question, match: float, resume_text: str) -> str:
    if match >= 0.35:
        return "简历关键词与题目高度重叠"
    if q.freq >= 3:
        return "岗位高频题,建议优先准备"
    if q.topic in {"RAG", "Agent", "MCP/协议"} and any(
        t in _tokens(resume_text) for t in ("rag", "agent", "langchain", "python")
    ):
        return f"岗位核心主题({q.topic})与简历技能栈相关"
    return "岗位常见题,作为补充准备"


def build_followup_chains(
    predicted: list[dict],
    resume_text: str,
    *,
    max_chains: int = 5,
) -> list[FollowUpChain]:
    anchors = resume_anchors(resume_text)
    primary = anchors[0] if anchors else "简历中的核心项目"
    chains: list[FollowUpChain] = []
    templates = [
        "你在{anchor}里具体负责哪一块?数据流/调用链能画一下吗?",
        "如果线上效果不达预期,你会从哪些维度排查?",
        "这个方案相比朴素 baseline,指标提升了多少?怎么验证的?",
        "当时最大的技术 trade-off 是什么?为什么这样选?",
        "如果重做一版,你会改架构的哪一层?",
    ]
    for item in predicted[:max_chains]:
        grounded = item["resume_match"] >= 0.2
        chains.append(
            FollowUpChain(
                seed_question=item["text"],
                resume_anchor=primary,
                followups=[t.format(anchor=primary) for t in templates[:4]],
                is_grounded=grounded,
            )
        )
    return chains


def gap_rows(resume_text: str, role: str, ranked: list[Question]) -> list[dict]:
    topics = {q.topic for q in ranked[:30]}
    rows: list[dict] = []
    checks = [
        ("RAG 工程", ["rag", "检索", "embedding", "向量"]),
        ("Agent 设计", ["agent", "react", "tool", "mcp"]),
        ("后端基础", ["redis", "mysql", "spring", "java"]),
        ("LLM 基础", ["transformer", "attention", "微调", "sft"]),
    ]
    resume_norm = normalize(resume_text)
    for dim, hints in checks:
        resume_hit = any(h in resume_norm for h in hints)
        topic_hit = any(
            (dim.startswith("RAG") and "RAG" in topics)
            or (dim.startswith("Agent") and "Agent" in topics)
            or (dim.startswith("后端") and "后端八股" in topics)
            or (dim.startswith("LLM") and "LLM基础" in topics)
            for _ in [0]
        )
        risk = "高" if topic_hit and not resume_hit else ("中" if topic_hit else "低")
        rows.append(
            {
                "dimension": dim,
                "resume_evidence": "简历有提及" if resume_hit else "简历未明显体现",
                "interview_risk": risk,
                "advice": f"对照高频{dim}题补项目表述与八股" if risk != "低" else "保持现有表述",
            }
        )
    if not rows:
        rows.append(
            {
                "dimension": role or "目标岗位",
                "resume_evidence": "待人工核对",
                "interview_risk": "中",
                "advice": "结合题库 Top 题逐条对照简历",
            }
        )
    return rows


def render_prep_package(
    *,
    role: str,
    resume_text: str,
    bank: dict,
    predicted: list[dict],
    chains: list[FollowUpChain],
    gaps: list[dict],
    generated_at: date | None = None,
) -> str:
    ref = (generated_at or date.today()).isoformat()
    lines = [
        f"# {role}岗位备考包",
        "",
        f"生成日期: {ref}",
        f"目标岗位: {role}",
        "",
        "## 1. 候选人定位(基于简历关键词)",
        "",
        "> 结合简历技能栈与岗位高频题,优先准备重叠度高的主题。",
        "",
        "### 简历摘要",
        "",
        resume_text.strip()[:800] or "(简历需视觉解析,请 Agent 补读图片/PDF)",
        "",
        "## 2. 岗位 Gap 分析",
        "",
        "| 维度 | 简历表现 | 面试风险 | 准备建议 |",
        "|---|---|---|---|",
    ]
    for row in gaps:
        lines.append(
            f"| {row['dimension']} | {row['resume_evidence']} | "
            f"{row['interview_risk']} | {row['advice']} |"
        )

    lines.extend(
        [
            "",
            "## 3. 题库概况",
            "",
            f"- 去重题目: {bank['question_count']}",
            f"- 原始帖数: {bank['post_count']}",
            f"- 完整题库: `question_bank.json`",
            f"- 高频报告: `frequency_report.md`",
            "",
            "## 4. 你可能会被问到(简历 × 高频)",
            "",
        ]
    )
    for i, item in enumerate(predicted[:15], 1):
        companies = "、".join(item["company_tags"]) or "未标注"
        lines.append(f"### {i}. {item['text']}")
        lines.append("")
        lines.append(
            f"- 匹配度: {item['resume_match']} · 综合分: {item.get('combined_score', item['resume_match'])} · "
            f"频次: {item['freq']} · 主题: {item['topic']} · 公司: {companies}"
        )
        lines.append(f"- 原因: {item['why']}")
        if item.get("source_refs"):
            lines.append(f"- 来源: `{item['source_refs'][0]}`")
        lines.append("")

    lines.extend(["## 5. 个性化追问链", ""])
    for i, chain in enumerate(chains[:5], 1):
        grounded = "已锚定简历" if chain.is_grounded else "通用追问(待补简历细节)"
        lines.append(f"### 链 {i}: {chain.seed_question[:50]}…")
        lines.append("")
        lines.append(f"锚点: {chain.resume_anchor} · {grounded}")
        lines.append("")
        for j, fu in enumerate(chain.followups, 1):
            lines.append(f"{j}. {fu}")
        lines.append("")

    lines.extend(
        [
            "## 6. 面试前速查",
            "",
            "- 优先刷第 4 节匹配度 ≥ 0.35 的题",
            "- 每个核心项目准备 1 个可量化结果",
            "- 对照 `frequency_report.md` 补岗位高频但简历未写的点",
            "",
        ]
    )
    return "\n".join(lines)
