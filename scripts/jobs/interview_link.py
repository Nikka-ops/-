"""Link job postings to interview posts (面经) and discover missing coverage."""
from __future__ import annotations

import re

from scripts.corpus.recency import RECENCY_WINDOW_DAYS, filter_recent
from scripts.discover.nowcoder_moments import search_nowcoder_moments
from scripts.jobs.connectors.registry import normalize_company_name
from scripts.jobs.models import JobPosting
from scripts.models import RawPost

_TITLE_NOISE = re.compile(
    r"(工程师|开发|岗位|职位|实习|校招|社招|专家|负责人|高级|资深|初级|中级)+$"
)


def _norm_company(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    canon = normalize_company_name(n)
    return (canon or n).lower()


def _company_match(post_company: str, job_company: str) -> bool:
    a = _norm_company(post_company)
    b = _norm_company(job_company)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _title_tokens(title: str) -> list[str]:
    raw = _TITLE_NOISE.sub("", (title or "").strip())
    parts = re.split(r"[/\\|\s·]+", raw)
    tokens: list[str] = []
    for p in parts:
        t = p.strip()
        if len(t) >= 2:
            tokens.append(t.lower())
    return tokens


def match_posts_to_job(job: JobPosting, posts: list[RawPost]) -> list[RawPost]:
    """Heuristic: same company + title tokens or company in post body."""
    matched: list[RawPost] = []
    tokens = _title_tokens(job.title)
    for post in posts:
        company = post.company or ""
        title_line = (getattr(post, "title", None) or "").strip()
        blob = f"{title_line}\n{post.raw_text or ''}\n{post.content_text or ''}"
        if not _company_match(company, job.company):
            if job.company and job.company in blob:
                pass
            else:
                continue
        if tokens and any(t in blob.lower() for t in tokens):
            matched.append(post)
        elif _company_match(company, job.company):
            matched.append(post)
    return matched


def _attach_job_interview_meta(job: JobPosting, related: list[RawPost]) -> None:
    job.extra["interview_post_count"] = len(related)
    urls: list[str] = []
    snippets: list[str] = []
    for p in related[:5]:
        u = (p.url or "").strip()
        if u and u not in urls:
            urls.append(u)
        text = (p.raw_text or p.content_text or p.title or "").strip()
        if text:
            snippets.append(text[:400])
    job.extra["interview_post_urls"] = urls
    job.extra["interview_snippets"] = snippets[:3]


def attach_interview_context(
    jobs: list[JobPosting],
    bank_posts: list[RawPost],
    *,
    discover_missing: bool = True,
    max_discover_jobs: int = 30,
    max_per_query: int = 6,
    window_days: int = RECENCY_WINDOW_DAYS,
) -> dict:
    """Match jobs to cached bank posts; optionally discover 牛客 moments for gaps."""
    recent_bank = filter_recent(bank_posts, window_days=window_days)
    meta: dict = {
        "matched_jobs": 0,
        "discovered_posts": 0,
        "discover_queries": 0,
    }

    for job in jobs:
        related = match_posts_to_job(job, recent_bank)
        if related:
            _attach_job_interview_meta(job, related)
            meta["matched_jobs"] += 1
        else:
            job.extra.setdefault("interview_post_count", 0)

    if not discover_missing:
        return meta

    gaps = [j for j in jobs if not j.extra.get("interview_post_count")][:max_discover_jobs]
    if not gaps:
        return meta

    for job in gaps:
        q = f"{job.company} {job.title} 面经".strip()
        if not q:
            continue
        meta["discover_queries"] += 1
        discovered, disc_meta = search_nowcoder_moments(
            [q],
            max_per_query=max_per_query,
            request_delay=0.35,
        )
        meta["discovered_posts"] += len(discovered)
        recent_disc = filter_recent(discovered, window_days=window_days)
        related = match_posts_to_job(job, recent_disc)
        if related:
            _attach_job_interview_meta(job, related)
            meta["matched_jobs"] += 1
        if disc_meta.get("per_query"):
            meta.setdefault("discover_meta", {"per_query": []})
            meta["discover_meta"]["per_query"].extend(disc_meta["per_query"])

    return meta
