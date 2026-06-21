"""Dedupe scraped posts before bank ingest."""
from __future__ import annotations

from scripts.models import RawPost


def post_dedupe_key(post: RawPost) -> str:
    url = (post.url or "").strip()
    if url and url != "https://www.nowcoder.com/":
        return url
    blob = (post.raw_text or post.content_text or post.locator_text or "").strip()
    return blob[:240] if blob else ""


def dedupe_raw_posts(posts: list[RawPost]) -> list[RawPost]:
    out: list[RawPost] = []
    seen: set[str] = set()
    for post in posts:
        key = post_dedupe_key(post)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(post)
    return out
