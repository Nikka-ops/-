"""Group scraped posts and questions by company and role taxonomy."""
from __future__ import annotations

from collections import defaultdict

from scripts.models import Question, RawPost

UNKNOWN = "未标注"


def _bucket(value: str | None) -> str:
    return (value or "").strip() or UNKNOWN


def group_posts_by_taxonomy(posts: list[RawPost]) -> dict[str, dict[str, list[RawPost]]]:
    """Return nested dict: company -> role -> posts."""
    grouped: dict[str, dict[str, list[RawPost]]] = defaultdict(lambda: defaultdict(list))
    for post in posts:
        grouped[_bucket(post.company)][_bucket(post.role)].append(post)
    return {c: dict(roles) for c, roles in sorted(grouped.items())}


def group_questions_by_taxonomy(questions: list[Question]) -> dict[str, dict[str, list[Question]]]:
    """Return nested dict: company -> role -> questions."""
    grouped: dict[str, dict[str, list[Question]]] = defaultdict(lambda: defaultdict(list))
    for q in questions:
        companies = q.company_tags or [UNKNOWN]
        roles = q.role_tags or [UNKNOWN]
        for company in companies:
            for role in roles:
                grouped[_bucket(company)][_bucket(role)].append(q)
    return {c: dict(roles) for c, roles in sorted(grouped.items())}


def taxonomy_summary(posts: list[RawPost]) -> list[dict]:
    """Flat summary rows for reporting: company, role, count, sources."""
    rows: list[dict] = []
    for company, roles in group_posts_by_taxonomy(posts).items():
        for role, bucket in roles.items():
            sources = sorted({p.source for p in bucket})
            rows.append(
                {
                    "company": company,
                    "role": role,
                    "count": len(bucket),
                    "sources": sources,
                }
            )
    return sorted(rows, key=lambda r: (-r["count"], r["company"], r["role"]))
