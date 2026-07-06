"""Download remote post images and OCR for 牛客 / generic image 面经."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from scripts.models import RawPost
from scripts.corpus.post_text_merge import merge_article_and_ocr, parse_ocr_pages, post_article_text
from scripts.ocr.xhs_images import (
    OCRPage,
    PageMerger,
    rapidocr_engine,
    XHSImageOCRProcessor,
)

_HTTP_URL = re.compile(r"^https?://", re.I)
_MIN_BODY_CHARS = 80


def _cache_key(post: RawPost) -> str:
    raw = (post.url or post.raw_text[:80] or "post").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def _remote_image_urls(post: RawPost) -> list[str]:
    urls: list[str] = []
    for item in post.asset_paths or []:
        s = str(item).strip()
        if _HTTP_URL.match(s):
            urls.append(s)
    return urls


def _local_image_paths(post: RawPost) -> list[Path]:
    paths: list[Path] = []
    for item in post.asset_paths or []:
        p = Path(str(item))
        if p.is_file():
            paths.append(p)
    return paths


def parse_ocr_pages(text: str) -> list[str]:
    from scripts.corpus.post_text_merge import parse_ocr_pages as _parse

    return _parse(text)


def _referer_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "xhscdn" in host or "xiaohongshu" in host:
        return "https://www.xiaohongshu.com/"
    if "nowcoder" in host:
        return "https://www.nowcoder.com/"
    return ""


_DOWNLOAD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def download_post_images(
    post: RawPost,
    *,
    asset_root: Path,
    http_get=None,
    timeout: int = 20,
) -> list[Path]:
    urls = _remote_image_urls(post)
    if not urls:
        return _local_image_paths(post)

    key = _cache_key(post)
    note_dir = asset_root / key
    note_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, url in enumerate(urls, start=1):
        path = note_dir / f"{index:03d}{_extension_from_url(url)}"
        if not path.is_file():
            try:
                headers = {"User-Agent": _DOWNLOAD_UA}
                ref = _referer_for_url(url)
                if ref:
                    headers["Referer"] = ref
                getter = http_get or requests.get
                resp = getter(url, headers=headers, timeout=timeout)
                resp.raise_for_status()
                path.write_bytes(resp.content)
            except Exception:
                continue
        if path.is_file():
            paths.append(path)
    return paths


def download_images_batch(
    posts: list[RawPost],
    *,
    asset_root: Path = Path("corpus_cache/assets/posts"),
) -> list[RawPost]:
    """Download remote images for all posts and update asset_paths to local paths.

    Decoupled from OCR — run this first so images are cached regardless of deep mode.
    """
    result: list[RawPost] = []
    for post in posts:
        if _remote_image_urls(post):
            paths = download_post_images(post, asset_root=asset_root)
            if paths:
                post.asset_paths = [str(p) for p in paths]
        result.append(post)
    return result


def ocr_image_paths(
    cache_key: str,
    image_paths: list[Path],
    *,
    ocr_root: Path,
    engine=None,
) -> list[OCRPage]:
    if not image_paths:
        return []
    processor = XHSImageOCRProcessor(ocr_root=ocr_root, engine=engine or rapidocr_engine())
    return processor.process(cache_key, image_paths)


def enrich_post_with_image_ocr(
    post: RawPost,
    *,
    asset_root: Path = Path("corpus_cache/assets/posts"),
    ocr_root: Path = Path("corpus_cache/ocr/posts"),
    enable_ocr: bool = True,
    min_body_chars: int = _MIN_BODY_CHARS,
    network: bool = True,
) -> RawPost:
    """OCR image pages when body is short; merge into image_ocr_text / raw_text."""
    if not enable_ocr:
        return post

    primary = (post.image_ocr_text or post.content_text or post.raw_text or "").strip()
    has_ocr = bool((post.image_ocr_text or "").strip())
    images = _remote_image_urls(post) or _local_image_paths(post)
    if not images:
        return post

    if has_ocr and len(primary.replace(" ", "")) >= min_body_chars:
        return post

    key = _cache_key(post)
    if not network:
        paths = _local_image_paths(post)
        if not paths:
            return post
        pages = ocr_image_paths(key, paths, ocr_root=ocr_root)
        merged = PageMerger().merge([p.text for p in pages])
        if not merged.strip():
            return post
        post.image_ocr_text = merged
        article = post_article_text(post) or primary
        combined = merge_article_and_ocr(article, merged)
        post.raw_text = combined if combined else (primary or merged)
        post.content_text = post.raw_text
        post.asset_paths = [str(p) for p in paths]
        post.extraction_quality = "ocr_ok"
        return post

    paths = download_post_images(post, asset_root=asset_root)
    if not paths:
        return post

    key = _cache_key(post)
    pages = ocr_image_paths(key, paths, ocr_root=ocr_root)
    merged = PageMerger().merge([p.text for p in pages])
    if not merged.strip():
        post.needs_vision_fallback = True
        post.extraction_quality = post.extraction_quality or "text_only"
        local_assets = [str(p) for p in paths]
        if local_assets:
            post.asset_paths = local_assets
        return post

    post.image_ocr_text = merged
    article = post_article_text(post) or primary
    combined = merge_article_and_ocr(article, merged)
    post.raw_text = combined if combined else (primary or merged)
    post.content_text = post.raw_text
    post.post_type = "image" if len(primary) < min_body_chars else "mixed"
    post.asset_paths = [str(p) for p in paths]
    post.needs_vision_fallback = any(p.needs_vision for p in pages)
    post.extraction_quality = "ocr_low_quality" if post.needs_vision_fallback else "ocr_ok"
    return post


def enrich_posts_image_ocr(
    posts: list[RawPost],
    *,
    enable_ocr: bool = True,
) -> list[RawPost]:
    if not enable_ocr:
        return posts
    return [enrich_post_with_image_ocr(p, enable_ocr=True) for p in posts]
