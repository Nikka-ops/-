"""Map scraped posts to preset tech roles and filter bank ingest by target role."""
from __future__ import annotations

import re

from scripts.corpus.tech_roles import TECH_ROLES, TechRole, get_tech_role
from scripts.models import RawPost

_SPACE = re.compile(r"\s+")
_ROLE_NOISE = re.compile(
    r"(?:面经|面试|实习|校招|社招|秋招|春招|经验|分享|记录|汇总|整理|攻略|一面|二面|三面)+",
    re.IGNORECASE,
)

# Ordered: more specific markers win over broad ones (e.g. 测开 before 大模型).
_ROLE_HINT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    [
        (re.compile(r"测开|测试开发|自动化测试|QA工程师?", re.I), "qa"),
        (re.compile(r"客户端|Android|iOS|Flutter", re.I), "client"),
        (re.compile(r"前端|React|Vue", re.I), "frontend"),
        (re.compile(r"基础架构|SRE|运维开发", re.I), "infra"),
        (re.compile(r"安全工程师|渗透|网络安全", re.I), "security"),
        (re.compile(r"数据开发|数仓|ETL|Spark|Hive", re.I), "data"),
        (re.compile(r"数据分析|BI分析师", re.I), "data_analyst"),
        (re.compile(r"Agent开发|Agent\s*工程师|工具调用", re.I), "ai_app"),
        (re.compile(r"AI应用|RAG|LangChain", re.I), "ai_app"),
        (re.compile(r"大模型|LLM|预训练|SFT|RLHF", re.I), "llm"),
        (re.compile(r"算法工程师|机器学习|深度学习|CV|NLP", re.I), "algorithm"),
        (re.compile(r"后端|Java开发|Go开发|微服务", re.I), "backend"),
        (re.compile(r"测试工程师", re.I), "qa"),
    ]
)


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "").strip().lower())


def _aliases(preset: TechRole) -> set[str]:
    items = {_norm(preset.search_as), _norm(preset.label)}
    for kw in preset.keywords:
        items.add(_norm(kw))
    return {a for a in items if len(a) >= 2}


def resolve_target_preset(target_role: str) -> TechRole | None:
    target_norm = _norm(target_role)
    if not target_norm:
        return None
    for preset in TECH_ROLES:
        if target_norm in _aliases(preset) or any(
            target_norm in a or a in target_norm for a in _aliases(preset)
        ):
            return preset
    return None


def infer_preset_from_text(text: str) -> TechRole | None:
    blob = (text or "").strip()
    if not blob:
        return None
    for pattern, role_id in _ROLE_HINT_PATTERNS:
        if pattern.search(blob):
            return get_tech_role(role_id)
    norm = _norm(blob)
    best: TechRole | None = None
    best_len = 0
    for preset in TECH_ROLES:
        for alias in _aliases(preset):
            if alias and alias in norm and len(alias) > best_len:
                best_len = len(alias)
                best = preset
    return best if best_len >= 3 else None


def refine_extracted_role(
    *,
    title: str = "",
    tags: list[str] | None = None,
    desc: str = "",
    parsed_role: str | None = None,
) -> str | None:
    """Pick a cleaner role label using preset taxonomy."""
    parts = [title, parsed_role or "", desc]
    if tags:
        parts.extend(tags)
    combined = "\n".join(p for p in parts if p and str(p).strip())
    inferred = infer_preset_from_text(combined)
    if inferred:
        return inferred.search_as
    if parsed_role and str(parsed_role).strip():
        cleaned = _ROLE_NOISE.sub("", str(parsed_role)).strip()
        return cleaned or None
    return None


def post_text_blob(post: RawPost) -> str:
    parts = [
        post.raw_text or "",
        post.content_text or "",
        post.locator_text or "",
        post.image_ocr_text or "",
        post.role or "",
    ]
    return "\n".join(p for p in parts if p and str(p).strip())


def infer_preset_from_post(post: RawPost) -> TechRole | None:
    """Prefer scraped role label, then title line, then full body."""
    if (post.role or "").strip():
        hit = infer_preset_from_text(post.role)
        if hit:
            return hit
    raw = (post.raw_text or post.content_text or "").strip()
    if raw:
        first = raw.splitlines()[0].strip()[:160]
        hit = infer_preset_from_text(first)
        if hit:
            return hit
    return infer_preset_from_text(post_text_blob(post))


def score_post_for_bank(post: RawPost, target_role: str) -> tuple[float, bool]:
    """Return (score 0–1, role_mismatch). mismatch=True when confident wrong role."""
    target = resolve_target_preset(target_role)
    if not target:
        return 1.0, False

    inferred = infer_preset_from_post(post)
    if inferred is None:
        target_aliases = _aliases(target)
        norm_blob = _norm(post_text_blob(post))
        if any(a in norm_blob for a in target_aliases):
            return 0.7, False
        return 0.55, False

    if inferred.id == target.id:
        return 1.0, False

    related_groups = [
        {"ai_app", "agent", "llm"},
        {"algorithm", "llm"},
        {"data", "data_analyst"},
    ]
    for group in related_groups:
        if inferred.id in group and target.id in group:
            return 0.45, False

    return 0.15, True


def filter_posts_for_bank(
    posts: list[RawPost],
    target_role: str,
    *,
    min_score: float = 0.2,
) -> tuple[list[RawPost], list[RawPost]]:
    kept: list[RawPost] = []
    dropped: list[RawPost] = []
    for post in posts:
        score, mismatch = score_post_for_bank(post, target_role)
        if mismatch and score < min_score:
            dropped.append(post)
        else:
            kept.append(post)
    return kept, dropped


def annotate_post_role(post: RawPost) -> RawPost:
    """Fill missing role from text; do not overwrite labels already set at scrape."""
    if (post.role or "").strip():
        return post
    refined = refine_extracted_role(
        title=(post.raw_text or "")[:120],
        desc=post_text_blob(post),
        parsed_role=post.role,
    )
    if refined:
        post.role = refined
    return post


def annotate_post_company(post: RawPost) -> RawPost:
    if (post.company or "").strip():
        return post
    from scripts.corpus.classify import infer_company_from_text

    company = infer_company_from_text(post_text_blob(post))
    if company:
        post.company = company
    return post


def annotate_post(post: RawPost) -> RawPost:
    return annotate_post_company(annotate_post_role(post))
