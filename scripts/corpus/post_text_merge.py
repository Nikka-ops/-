"""Merge article caption with image OCR for display and ingest."""
from __future__ import annotations

import re

from scripts.corpus.post_format import clean_post_text

_OCR_PAGE = re.compile(r"\[图片 OCR 第\s*(\d+)\s*页\]\s*\n?", re.I)


def parse_ocr_pages(text: str) -> list[str]:
    if not text or "[图片 OCR 第" not in text:
        return []
    parts = _OCR_PAGE.split(text.strip())
    if len(parts) < 2:
        return []
    pages: list[str] = []
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):
            pages.append(parts[i + 1].strip())
            i += 2
        else:
            break
    return pages


def strip_ocr_page_markers(text: str) -> str:
    if not text or "[图片 OCR 第" not in text:
        return (text or "").strip()
    return _OCR_PAGE.sub("", text).strip()


def ocr_pages_plain(ocr_merged: str) -> list[str]:
    pages = parse_ocr_pages(ocr_merged)
    if pages:
        return [p.strip() for p in pages if p.strip()]
    plain = strip_ocr_page_markers(ocr_merged)
    return [plain] if plain else []


def merge_article_and_ocr(article: str, ocr_merged: str | None) -> str:
    """Combine post caption/title with OCR body (no page labels in output)."""
    article_clean = clean_post_text(article or "").strip()
    ocr_pages = ocr_pages_plain(ocr_merged or "")
    ocr_body = "\n\n".join(ocr_pages).strip()

    if not article_clean:
        return ocr_body
    if not ocr_body:
        return article_clean

    a_norm = re.sub(r"\s+", "", article_clean)
    o_norm = re.sub(r"\s+", "", ocr_body)
    if a_norm and a_norm in o_norm:
        return ocr_body
    if o_norm and o_norm in a_norm:
        return article_clean

    return f"{article_clean}\n\n{ocr_body}".strip()


def post_article_text(post) -> str:
    """User-written caption / title block (not OCR)."""
    locator = clean_post_text((post.locator_text or "").strip())
    if locator:
        return locator
    raw = (post.raw_text or post.content_text or "").strip()
    if raw and "[图片 OCR 第" not in raw:
        return clean_post_text(raw)
    return ""
