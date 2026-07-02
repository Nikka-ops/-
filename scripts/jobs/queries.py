"""JD search queries (招聘关键词，不含面经后缀)."""
from __future__ import annotations

from scripts.corpus.tech_roles import canonical_role_id, get_tech_role, resolve_role_label

# 精准搜索词：直接命中目标岗位的关键词
_ROLE_TERMS: dict[str, tuple[str, ...]] = {
    "data": (
        "数据开发",
        "数仓工程师",
        "大数据开发",
        "数据工程师",
        "ETL工程师",
        "Spark开发",
        "Flink开发",
        "数据架构师",
        "数据中台",
        "实时数仓",
        "离线数仓",
        "数据治理",
        "数据建模",
    ),
    "ai_app": (
        "Agent开发",
        "AI应用开发",
        "RAG工程师",
        "大模型应用",
        "智能体开发",
        "LLM应用工程师",
        "AI应用工程师",
        "多智能体",
    ),
}


def build_job_search_queries(
    role_id: str,
    *,
    role_label: str = "",
    companies: list[str] | None = None,
) -> list[str]:
    rid = canonical_role_id(role_id) or role_id
    label = role_label or resolve_role_label(role_id=rid)
    preset = get_tech_role(rid)
    out: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        text = " ".join(q.split())
        if not text or "面经" in text or text in seen:
            return
        seen.add(text)
        out.append(text)

    if preset:
        add(preset.search_as)
        for kw in preset.keywords:
            add(kw)
    for term in _ROLE_TERMS.get(rid, ()):
        add(term)
    add(label)
    for company in companies or []:
        c = company.strip()
        if c:
            add(f"{c} {label}")
    return out
