"""Build Agent handoff artifacts — AI steps 4–8 per original SKILL design."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.corpus.group import taxonomy_summary
from scripts.models import Question, RawPost
from scripts.resume_extract import ResumeExtraction

_AGENT_STEPS = [
    "4. 内容级相关性判定(读 RawPost 正文,对照岗位+简历)",
    "5. 题目抽取与 refinement(可基于 question_bank 候选,补 vision/OCR 失败帖)",
    "5b. 确认时效过滤结果(已由 Python 执行,复核边界案例)",
    "6. 去重排序复核(已由 Python 粗排,可按语义再合并)",
    "7. 项目锚定推理 → FollowUpChain(is_grounded)",
    "8. 按 SKILL.md 固定模板撰写 prep_package.md",
]

_CONSTRAINTS = [
    "禁止编造无 source_refs 的题目或追问",
    "needs_vision / needs_vision_fallback 的素材必须用视觉能力补读,不得猜测",
    "追问必须同时追溯到简历项目/技能 + 真实面经题",
    "数据源仅限牛客 + 小红书",
]


def posts_needing_vision(posts: list[RawPost]) -> list[dict]:
    rows: list[dict] = []
    for post in posts:
        if not post.needs_vision_fallback and post.extraction_quality != "ocr_low_quality":
            continue
        rows.append(
            {
                "source": post.source,
                "url": post.url,
                "asset_paths": list(post.asset_paths),
                "locator_text": (post.locator_text or "")[:600],
                "extraction_quality": post.extraction_quality,
                "needs_vision_fallback": post.needs_vision_fallback,
            }
        )
    return rows


def build_agent_context(
    *,
    role: str,
    companies: list[str],
    posts: list[RawPost],
    ranked: list[Question],
    bank: dict,
    paths: dict,
    resume: ResumeExtraction | None,
    resume_text: str,
    ingest_mode: str,
    sources: dict,
) -> dict:
    return {
        "generated_at": date.today().isoformat(),
        "prep_mode": "agent",
        "role": role,
        "companies": companies,
        "ingest_mode": ingest_mode,
        "sources": sources,
        "paths": paths,
        "post_count": len(posts),
        "question_count": len(ranked),
        "taxonomy": taxonomy_summary(posts),
        "resume": {
            "text": resume_text,
            "needs_vision": bool(resume and resume.needs_vision),
            "asset_path": resume.asset_path if resume else "",
            "ocr_used": bool(resume and resume.ocr_used),
            "ocr_confidence": resume.ocr_confidence if resume else 0.0,
        },
        "posts_needing_vision": posts_needing_vision(posts),
        "question_candidates": [
            {
                "text": q.text,
                "freq": q.freq,
                "topic": q.topic,
                "company_tags": q.company_tags,
                "role_tags": q.role_tags,
                "source_refs": q.source_refs,
                "modality_origin": q.modality_origin,
            }
            for q in ranked[:50]
        ],
        "agent_steps": _AGENT_STEPS,
        "constraints": _CONSTRAINTS,
        "outputs_expected": {
            "questions_refined": "corpus_cache/questions_raw.json (via save_questions)",
            "questions_ranked": "corpus_cache/questions_ranked.json",
            "prep_package": "corpus_cache/prep_package.md",
        },
        "bank_summary": {
            "role": bank.get("role"),
            "question_count": bank.get("question_count"),
            "top_questions": [q["text"] for q in bank.get("questions", [])[:15]],
        },
    }


def render_agent_handoff_md(ctx: dict) -> str:
    lines = [
        "# Agent 交接包 · InterviewRadar",
        "",
        f"生成日期: {ctx['generated_at']}",
        f"目标岗位: {ctx['role']}",
        "",
        "## 分工说明",
        "",
        "Python 已完成: 采集 → 粗抽题 → 语义合并 → 频次排序 → `question_bank.json`。",
        "**以下步骤必须由 Agent(LLM/视觉)完成**,对齐原项目设计 — 不要用规则模板冒充备考包。",
        "",
        "## 1. 简历",
        "",
    ]
    resume = ctx.get("resume") or {}
    if resume.get("needs_vision") and not resume.get("text"):
        lines.append(
            f"- **需要视觉解析**: `{resume.get('asset_path')}` "
            "(OCR 不足,请用视觉能力读取后写结构化摘要)"
        )
    elif resume.get("text"):
        lines.append("### 已提取文本(供参考,可再结构化)")
        lines.append("")
        lines.append(resume["text"][:2000])
    else:
        lines.append("- 未提供简历;备考包可只做岗位通用高频题。")

    lines.extend(["", "## 2. 待视觉补读的帖子", ""])
    vision_posts = ctx.get("posts_needing_vision") or []
    if vision_posts:
        for row in vision_posts[:20]:
            assets = ", ".join(row.get("asset_paths") or []) or "(无本地路径)"
            lines.append(f"- [{row.get('source')}] {row.get('url')}")
            lines.append(f"  - assets: {assets}")
            lines.append(f"  - locator: {(row.get('locator_text') or '')[:200]}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 3. 题库路径", ""])
    for key, val in (ctx.get("paths") or {}).items():
        lines.append(f"- {key}: `{val}`")

    lines.extend(["", "## 4. 公司 × 岗位召回", ""])
    lines.append("| 公司 | 岗位 | 帖数 |")
    lines.append("|---|---|---|")
    for row in ctx.get("taxonomy") or []:
        lines.append(f"| {row['company']} | {row['role']} | {row['count']} |")

    lines.extend(["", "## 5. 高频题候选(粗排,供 Step 5–7 精炼)", ""])
    for i, q in enumerate(ctx.get("question_candidates") or [], 1):
        companies = "、".join(q.get("company_tags") or []) or "未标注"
        lines.append(f"{i}. {q['text']} (freq={q['freq']}, {companies})")

    lines.extend(["", "## 6. Agent 待执行步骤", ""])
    for step in ctx.get("agent_steps") or []:
        lines.append(f"- {step}")

    lines.extend(["", "## 7. 约束", ""])
    for c in ctx.get("constraints") or []:
        lines.append(f"- {c}")

    lines.extend(
        [
            "",
            "## 8. 产出",
            "",
            "请按 `SKILL.md` 备考包固定模板撰写,保存到:",
            "",
            f"- `{ctx.get('outputs_expected', {}).get('prep_package', 'corpus_cache/prep_package.md')}`",
            "",
            "并更新 `questions_raw.json` / `questions_ranked.json`(如需精炼题目)。",
            "",
        ]
    )
    return "\n".join(lines)


def write_agent_handoff(
    cache_root: Path,
    slug: str,
    ctx: dict,
) -> tuple[Path, Path]:
    d = cache_root / slug
    d.mkdir(parents=True, exist_ok=True)
    json_path = d / "agent_context.json"
    md_path = d / "agent_handoff.md"
    json_path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_agent_handoff_md(ctx), encoding="utf-8")
    return md_path, json_path
