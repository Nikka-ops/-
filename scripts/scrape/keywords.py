"""Search keyword lists for Xiaohongshu / Nowcoder."""
from __future__ import annotations

from scripts.corpus.classify import classify_search_queries
from scripts.corpus.tech_roles import canonical_role_id, resolve_role_label

# 小红书搜索：数据开发用短词（用户口语「数开」），比牛客长 query 更贴笔记标题
_DATA_XHS_CORE: tuple[str, ...] = (
    "数开面经",
    "数开 面经",
    "数开一面",
    "数开二面",
    "数开三面",
    "数仓面经",
    "数仓 面经",
    "数仓一面",
    "数据开发面经",
    "数据开发 面经",
    "数据开发一面",
    "数据开发二面",
    "大数据开发面经",
    "大数据开发 面经",
    "大数据开发一面",
    "大数据 面经",
    "ETL面经",
    "Spark面经",
    "Hive面经",
    "Flink面经",
    "数仓开发面经",
    "离线数仓面经",
    "实时数仓面经",
    "湖仓面经",
    "数据研发面经",
    "数据平台面经",
)


def _data_xhs_keywords(companies: list[str]) -> list[str]:
    out: list[str] = list(_DATA_XHS_CORE)
    seen = set(out)
    for company in companies:
        c = company.strip()
        if not c:
            continue
        for tpl in (
            f"{c} 数开面经",
            f"{c} 数开 面经",
            f"{c} 数开一面",
            f"{c} 数据开发面经",
            f"{c} 数仓面经",
            f"{c} 大数据开发面经",
        ):
            if tpl not in seen:
                seen.add(tpl)
                out.append(tpl)
    return out


def nowcoder_queries_for_role(role_id: str, companies: list[str]) -> list[str]:
    role_label = resolve_role_label(role_id=role_id)
    return classify_search_queries(
        roles=[role_label],
        companies=companies or None,
        role_id=role_id,
    )


def xhs_keywords_for_role(role_id: str, companies: list[str]) -> list[str]:
    """Xiaohongshu search keywords (short, 面经-oriented)."""
    rid = canonical_role_id(role_id) or (role_id or "").strip()
    if rid == "data":
        return _data_xhs_keywords(companies or [])

    out: list[str] = []
    seen: set[str] = set()
    for q in nowcoder_queries_for_role(role_id, companies):
        text = q.strip()
        if not text:
            continue
        if "面经" not in text:
            text = f"{text} 面经"
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def xhs_core_keywords_for_role(role_id: str) -> list[str]:
    """Core XHS keywords without per-company expansion (faster daily sweep)."""
    rid = canonical_role_id(role_id) or (role_id or "").strip()
    if rid == "data":
        return list(_DATA_XHS_CORE)
    label = resolve_role_label(role_id=rid)
    return [f"{label} 面经", f"{label} 一面", f"{label} 二面"]


def merged_nowcoder_queries_for_roles(role_ids: list[str], companies: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for role_id in role_ids:
        for q in nowcoder_queries_for_role(role_id, companies):
            text = q.strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def merged_xhs_keywords_for_roles(role_ids: list[str], companies: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for role_id in role_ids:
        for k in xhs_keywords_for_role(role_id, companies):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out
