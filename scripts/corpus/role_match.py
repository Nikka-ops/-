"""Role inference + focus-role match. AI path in post_filter.py; this is the offline fallback."""
from __future__ import annotations

import re

from scripts.corpus.tech_roles import TECH_ROLES, TechRole, canonical_role_id, get_tech_role
from scripts.models import RawPost

_FOCUS = frozenset({"data", "ai_app"})
_HINTS = (
    (re.compile(r"测开|测试开发|QA工程师", re.I), "qa"),
    (re.compile(r"后端|后台开发|Java开发|Go开发|C\+\+开发|服务端开发", re.I), "backend"),
    (re.compile(r"前端|React|Vue|H5开发", re.I), "frontend"),
    (re.compile(r"嵌入式|MCU|单片机", re.I), "client"),
    (re.compile(r"外贸|海关|拓客|跨境", re.I), "product"),
    (re.compile(r"数据分析|BI分析|商业分析", re.I), "data_analyst"),
    (re.compile(r"Agent|RAG|MCP|LangChain|智能体", re.I), "ai_app"),
    (re.compile(r"数据开发|数仓|数开|ETL|数据研发|Hive|Flink|湖仓|数仓工程师|大数据开发", re.I), "data"),
    (re.compile(r"大模型|LLM|SFT", re.I), "llm"),
    (re.compile(r"算法|机器学习", re.I), "algorithm"),
)
_WRONG = {
    "data": {"data_analyst", "ai_app", "llm", "backend", "frontend", "algorithm", "qa", "client", "product"},
    "ai_app": {"backend", "frontend", "algorithm", "qa", "client", "data", "data_analyst", "product"},
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())


def _aliases(p: TechRole) -> set[str]:
    return {_norm(p.search_as), _norm(p.label)} | {_norm(k) for k in p.keywords if len(k) >= 2}


def resolve_target_preset(role: str) -> TechRole | None:
    n = _norm(role)
    for p in TECH_ROLES:
        if n in _aliases(p) or any(n in a or a in n for a in _aliases(p)):
            return p
    return None


def infer_preset_from_text(text: str) -> TechRole | None:
    t = (text or "").strip()
    if not t:
        return None
    for pat, rid in _HINTS:
        if pat.search(t):
            preset = get_tech_role(rid)
            if preset:
                return preset
    n = _norm(t)
    best, nlen = None, 0
    for p in TECH_ROLES:
        for a in _aliases(p):
            if len(a) >= 3 and a in n and len(a) > nlen:
                best, nlen = p, len(a)
    return best


def post_text_blob(post: RawPost) -> str:
    return "\n".join(x for x in (post.raw_text, post.content_text, post.locator_text, post.image_ocr_text, post.role) if x)


def post_combined_text(post: RawPost) -> str:
    return post_text_blob(post).strip()


def _body_text(post: RawPost, limit: int = 600) -> str:
    return "\n".join(x for x in (post.raw_text, post.content_text, post.locator_text, post.image_ocr_text) if x)[:limit]


def _head(post: RawPost) -> str:
    raw = (post.raw_text or post.content_text or post.role or "").strip()
    return raw.splitlines()[0][:160] if raw else ""


def infer_preset_from_post(post: RawPost) -> TechRole | None:
    """Title / explicit role only — do not scan full body (avoids Spark/agent bleed)."""
    if post.role and (h := infer_preset_from_text(str(post.role))):
        return h
    return infer_preset_from_text(_head(post))


def refine_extracted_role(*, title: str = "", tags: list[str] | None = None, desc: str = "", parsed_role: str | None = None) -> str | None:
    if title and (h := infer_preset_from_text(title)):
        return h.search_as
    extra = "\n".join(x for x in ((tags or []) + [parsed_role or ""]) if x)
    if extra and (h := infer_preset_from_text(extra)):
        return h.search_as
    return (parsed_role or "").strip() or None


def matches_target_role(post: RawPost, target_role: str) -> bool:
    """Offline fallback. Primary filtering is done by DeepSeek in post_filter.py."""
    tgt = resolve_target_preset(target_role)
    if not tgt:
        return True
    tid = canonical_role_id(tgt.id)

    # Check title for obvious wrong role
    head = _head(post)
    th = infer_preset_from_text(head)
    if th and tid in _FOCUS and th.id in _WRONG.get(tid, set()):
        return False
    if th and th.id == tgt.id:
        return True

    # Check explicit role field
    if post.role:
        pr = infer_preset_from_text(str(post.role))
        if pr and tid in _FOCUS and pr.id in _WRONG.get(tid, set()):
            return False
        if pr and canonical_role_id(pr.id) == tid:
            return True

    # Body keyword scan for focus roles
    if tid in _FOCUS:
        body = _body_text(post)
        # Data role keywords
        if tid == "data" and re.search(r"数据开发|数仓|数开|ETL|Spark|Hive|Flink|大数据|数据研发", body, re.I):
            return True
        # AI app role keywords
        if tid == "ai_app" and re.search(r"Agent|RAG|MCP|LangChain|智能体", body, re.I):
            return True

    # Default: trust scrape query pre-filtering
    inf = infer_preset_from_post(post)
    if inf and tid in _FOCUS and inf.id in _WRONG.get(tid, set()):
        return False
    return True


def filter_posts_for_bank(posts: list[RawPost], target_role: str, **_) -> tuple[list[RawPost], list[RawPost]]:
    kept = [p for p in posts if matches_target_role(p, target_role)]
    return kept, [p for p in posts if p not in kept]


def annotate_post(post: RawPost) -> RawPost:
    from scripts.corpus.classify import infer_company_from_text
    from scripts.corpus.company_normalize import normalize_company_name

    head = _head(post)
    if r := refine_extracted_role(title=head, parsed_role=post.role):
        post.role = r
    if not (post.company or "").strip():
        if c := infer_company_from_text(post_text_blob(post)):
            post.company = normalize_company_name(c) or ""
    elif post.company:
        post.company = normalize_company_name(post.company) or ""
    return post
