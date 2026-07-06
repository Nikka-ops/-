"""Serialize RawPost for Web UI feed (full 面经 cards)."""
from __future__ import annotations

import re
from collections import Counter

from scripts.corpus.post_format import (
    clean_post_text,
    collect_image_urls,
    format_body_html,
    resolve_source_url,
    strip_duplicate_title,
)
from scripts.corpus.post_text_merge import merge_article_and_ocr, post_article_text, strip_ocr_page_markers
from scripts.corpus.company_normalize import normalize_company_name
from scripts.corpus.role_match import matches_target_role
from scripts.discover.nowcoder_detail import enrich_nowcoder_text, extract_uuid_from_url, needs_full_fetch
from scripts.models import RawPost

_UNKNOWN = "未标注"


def post_company(post: RawPost) -> str:
    c = (post.company or "").strip()
    if not c:
        from scripts.corpus.classify import infer_company_from_text

        blob = "\n".join(
            p for p in (post.raw_text, post.content_text, post.locator_text, post.image_ocr_text) if p
        )
        c = infer_company_from_text(blob) or ""
    normalized = normalize_company_name(c) or ""
    return normalized or _UNKNOWN


def _primary_text(post: RawPost) -> str:
    article = post_article_text(post)
    ocr = (post.image_ocr_text or "").strip()
    if ocr:
        merged = merge_article_and_ocr(article, ocr)
        if merged:
            return merged
    for field in (post.content_text, post.raw_text):
        if field and str(field).strip():
            text = strip_ocr_page_markers(str(field).strip())
            if text:
                return text
    return article


def post_title(post: RawPost, max_len: int = 72) -> str:
    text = clean_post_text(_primary_text(post))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines:
        if len(line) >= 6 and (
            "面经" in line
            or "面试" in line
            or re.search(r"[一二三四五]面", line)
        ):
            return line[:max_len] + ("…" if len(line) > max_len else "")
    for line in lines:
        line = line.strip()
        if len(line) >= 4:
            return line[:max_len] + ("…" if len(line) > max_len else "")
    images = collect_image_urls(post.to_dict())
    if images:
        return "图片面经"
    return "面经分享"


def post_preview(post: RawPost, max_len: int = 220) -> str:
    title = post_title(post, max_len=200)
    text = strip_duplicate_title(title, clean_post_text(_primary_text(post)))
    flat = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    if not flat:
        images = collect_image_urls(post.to_dict())
        if images:
            return f"共 {len(images)} 页图片面经，点击查看"
        return ""
    if len(flat) <= max_len:
        return flat
    return flat[:max_len].rstrip() + "…"


def company_options(posts: list[RawPost]) -> list[dict]:
    counts: Counter[str] = Counter()
    for post in posts:
        counts[post_company(post)] += 1
    rows = [{"name": name, "count": count} for name, count in counts.items()]
    rows.sort(key=lambda r: (-r["count"], r["name"]))
    named = [r for r in rows if r["name"] != _UNKNOWN]
    unknown = [r for r in rows if r["name"] == _UNKNOWN]
    return named + unknown


def company_options_from_dicts(rows: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[row.get("company_label") or _UNKNOWN] += 1
    named = [{"name": name, "count": count} for name, count in counts.items()]
    named.sort(key=lambda r: (-r["count"], r["name"]))
    known = [r for r in named if r["name"] != _UNKNOWN]
    unknown = [r for r in named if r["name"] == _UNKNOWN]
    return known + unknown


def enrich_post_dict(post: RawPost, bank_role: str | None = None, *, for_display: bool = False) -> dict:
    work = post
    images_early = collect_image_urls(post.to_dict())
    # Only run OCR during ingest (for_display=False). Display/API paths skip OCR to avoid
    # loading ONNX models on every request, which causes multi-second hangs.
    if images_early and not (post.image_ocr_text or "").strip() and not for_display:
        from scripts.ocr.post_images import enrich_post_with_image_ocr

        work = enrich_post_with_image_ocr(post, network=True)

    d = work.to_dict()
    title = post_title(work)
    primary = _primary_text(work)

    if work.source == "nowcoder":
        uuid = extract_uuid_from_url(work.url)
        if uuid and needs_full_fetch(primary):
            if for_display:
                from scripts.discover.nowcoder_detail import read_cached_nowcoder_text

                enriched = read_cached_nowcoder_text(uuid)
            else:
                enriched = enrich_nowcoder_text(work.url, title, primary)
            if enriched and len(enriched) > len(primary):
                primary = enriched
                d["raw_text"] = enriched
                d["content_text"] = enriched

    images = collect_image_urls(d)
    display_body = strip_duplicate_title(title, clean_post_text(strip_ocr_page_markers(primary)))
    text_chars = len(display_body.replace(" ", ""))

    d["title"] = title
    d["preview"] = post_preview(work)
    d["company_label"] = post_company(work)
    d["role_label"] = (work.role or "").strip() or "未标注岗位"
    d["display_text"] = display_body
    d["display_html"] = format_body_html(primary, title=title)
    d["image_urls"] = images
    d["image_page_count"] = len(images)
    d["has_images"] = bool(images)
    d["images_only"] = bool(images) and text_chars < 80
    d["needs_ocr"] = (
        work.source in {"xiaohongshu", "nowcoder"}
        and images
        and not (work.image_ocr_text or "").strip()
        and work.extraction_quality == "text_only"
    )
    if bank_role:
        d["role_mismatch"] = not matches_target_role(work, bank_role)
    else:
        d["role_mismatch"] = False

    from scripts.corpus.post_text_merge import parse_ocr_pages

    ocr_pages = parse_ocr_pages(work.image_ocr_text or "")
    d["image_ocr_pages"] = ocr_pages
    if ocr_pages and len(ocr_pages) == len(images):
        d["image_page_ocr"] = ocr_pages

    source_url, source_label = resolve_source_url(
        source=work.source,
        url=work.url,
        title=title,
    )
    d["source_url"] = source_url
    d["source_link_label"] = source_label
    return d


def serialize_posts(
    posts: list[RawPost],
    bank_role: str | None = None,
    *,
    for_display: bool = False,
) -> list[dict]:
    work = posts
    if for_display:
        from scripts.corpus.post_filter import should_display_post

        work = [p for p in posts if should_display_post(p)]
    rows = [enrich_post_dict(p, bank_role=bank_role, for_display=for_display) for p in work]
    rows.sort(
        key=lambda r: (r.get("posted_at") or "", r.get("title") or ""),
        reverse=True,
    )
    return rows
