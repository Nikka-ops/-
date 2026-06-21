"""Search keyword lists for Xiaohongshu / Nowcoder."""
from __future__ import annotations

from scripts.corpus.classify import classify_search_queries
from scripts.corpus.tech_roles import resolve_role_label


def nowcoder_queries_for_role(role_id: str, companies: list[str]) -> list[str]:
    role_label = resolve_role_label(role_id=role_id)
    return classify_search_queries(
        roles=[role_label],
        companies=companies or None,
        role_id=role_id,
    )


def xhs_keywords_for_role(role_id: str, companies: list[str]) -> list[str]:
    """Shorter queries with 面经 suffix for Xiaohongshu search."""
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
