"""Fetch full 牛客动态正文（搜索 API 常带省略号 …）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scripts.config import cache_dir
from scripts.net.http_client import build_session
from scripts.net.retry import request_with_retry

_DETAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nowcoder.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
_ELLIPSIS_GAP = re.compile(r"…{1,3}|\.{3,}")
_UUID_IN_URL = re.compile(r"/feed/main/detail/([a-f0-9]{16,})", re.I)


def _cache_path(uuid: str) -> Path:
    root = cache_dir() / "nowcoder_full"
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-f0-9]", "", uuid.lower())
    return root / f"{safe}.txt"


def extract_uuid_from_url(url: str) -> str | None:
    m = _UUID_IN_URL.search(url or "")
    return m.group(1) if m else None


def _text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(".feed-content-text")
    if el:
        return el.get_text("\n", strip=True)
    m = re.search(r"window\.__INITIAL_STATE__=(\{.+?\});", html, re.DOTALL)
    if m:
        try:
            state = json.loads(m.group(1))
            content = (
                state.get("prefetchData", {})
                .get("2", {})
                .get("ssrCommonData", {})
                .get("contentData", {})
            )
            raw = content.get("content") or content.get("newContent") or ""
            if raw:
                return BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return ""


def read_cached_nowcoder_text(uuid: str) -> str:
    if not uuid:
        return ""
    cache = _cache_path(uuid)
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    return ""


def fetch_nowcoder_moment_full(uuid: str, *, use_cache: bool = True) -> str:
    if not uuid:
        return ""
    cache = _cache_path(uuid)
    if use_cache and cache.is_file():
        return cache.read_text(encoding="utf-8")
    url = f"https://www.nowcoder.com/feed/main/detail/{uuid}"
    session = build_session(extra_headers=_DETAIL_HEADERS)
    resp = request_with_retry(session, "GET", url, timeout=25)
    resp.raise_for_status()
    text = _text_from_html(resp.text)
    if text and use_cache:
        cache.write_text(text, encoding="utf-8")
    return text


def needs_full_fetch(text: str) -> bool:
    if not text:
        return True
    if _ELLIPSIS_GAP.search(text):
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 3 and not _ELLIPSIS_GAP.search(text):
        return False
    # search API 常把多题压成一行且带 …
    if re.search(r"\d+[\.\、]", text):
        return len(text) < 500
    return False


def enrich_nowcoder_text(url: str, title: str, body: str) -> str:
    uuid = extract_uuid_from_url(url)
    if not uuid or not needs_full_fetch(body):
        return body
    full = fetch_nowcoder_moment_full(uuid)
    if not full:
        return body
    if title and full.startswith(title.strip()):
        return full
    if title:
        return f"{title.strip()}\n{full}"
    return full
