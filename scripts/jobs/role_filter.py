"""Filter job postings to focus roles (数据开发/数仓 + Agent 开发)."""
from __future__ import annotations

from scripts.corpus.tech_roles import get_tech_role
from scripts.jobs.models import JobPosting

_DEFAULT_ROLE_IDS = ("data", "ai_app")

# ── 数据开发类关键词 ──────────────────────────────────────────────────
_DATA_STRONG = frozenset({
    # 核心岗位名
    "数据开发", "数据工程师", "数仓工程师", "大数据工程师", "数仓开发",
    "数据架构师", "数据架构", "数据中台", "数据基础",
    # 数仓概念
    "数仓", "数据仓库", "离线数仓", "实时数仓", "湖仓", "数据湖",
    "ods", "dwd", "dws", "ads", "数据分层", "数据建模", "数据治理",
    # 技术框架
    "spark", "flink", "hive", "hadoop", "etl", "elt",
    "kafka", "presto", "trino", "doris", "starrocks",
    "airflow", "datax", "sqoop", "flume", "kylin",
    # 通用大数据
    "大数据", "数据平台", "数据集成", "数据管道", "实时计算",
    "流计算", "批计算", "离线计算", "调度", "数据质量",
})

# ── AI应用开发类关键词 ────────────────────────────────────────────────
_AI_APP_STRONG = frozenset({
    # 核心岗位名
    "agent开发", "ai应用开发", "ai应用工程师", "智能体开发",
    "大模型应用", "llm应用", "ai产品工程师",
    # 技术框架
    "agent", "智能体", "rag", "langchain", "llamaindex",
    "langGraph", "autogen", "mcp", "tool use", "工具调用",
    "function call", "prompt engineering", "提示词工程",
    # 方向
    "ai应用", "ai 应用", "应用开发", "知识库", "向量检索",
    "向量数据库", "embedding", "rerank",
    "多智能体", "multi-agent",
})

# 标题/描述命中任一词即保留（大小写不敏感，多岗位模式）
_EXTRA_KEYWORDS: tuple[str, ...] = tuple(_DATA_STRONG | _AI_APP_STRONG)


def _keywords_for_roles(role_ids: list[str]) -> set[str]:
    out: set[str] = set(_EXTRA_KEYWORDS)
    for rid in role_ids:
        preset = get_tech_role(rid)
        if not preset:
            continue
        out.add(preset.search_as.lower())
        out.add(preset.label.lower())
        for kw in preset.keywords:
            out.add(kw.lower())
    return {k for k in out if len(k) >= 2}


def job_matches_focus_roles(job: JobPosting, role_ids: list[str] | None = None) -> bool:
    ids = role_ids or list(_DEFAULT_ROLE_IDS)
    tags = " ".join(job.tags or [])
    title = (job.title or "").lower()
    desc = (job.description or "").lower()
    blob = f"{title} {tags} {desc}".strip()
    if not blob:
        return False

    if len(ids) == 1:
        rid = ids[0]
        strong = _DATA_STRONG if rid == "data" else _AI_APP_STRONG if rid == "ai_app" else _keywords_for_roles(ids)
        # 有描述时在全 blob 匹配；无描述时只看标题（更宽松：含"数据"且无明显排除词即算入）
        if desc:
            return any(kw in blob for kw in strong)
        else:
            if any(kw in title for kw in strong):
                return True
            # 无描述兜底：标题含"数据"且不是明显的非数据开发岗
            if rid == "data" and "数据" in title:
                _exclude = {"分析师", "科学家", "产品经理", "运营", "增长", "商业分析", "策略"}
                return not any(ex in title for ex in _exclude)
            return False

    kws = _keywords_for_roles(ids)
    return any(kw in blob for kw in kws)


def filter_jobs_by_focus_roles(
    jobs: list[JobPosting],
    role_ids: list[str] | None = None,
) -> tuple[list[JobPosting], dict]:
    ids = role_ids or list(_DEFAULT_ROLE_IDS)
    kept = [j for j in jobs if job_matches_focus_roles(j, ids)]
    return kept, {
        "role_ids": ids,
        "before": len(jobs),
        "after": len(kept),
        "dropped": len(jobs) - len(kept),
    }
