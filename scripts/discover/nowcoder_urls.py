"""Discover 牛客 discuss detail URLs via search HTML (DuckDuckGo lite)."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from scripts.net.http_client import build_session
from scripts.net.retry import request_with_retry

_DISCUSS_ID = re.compile(r"nowcoder\.com/discuss/(\d+)")
_DDG_URL = "https://html.duckduckgo.com/html/"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def normalize_nowcoder_discuss_url(url: str) -> str | None:
    """Return canonical discuss URL or None if not a post detail page."""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "nowcoder.com" not in host:
        return None
    m = _DISCUSS_ID.search(url)
    if not m:
        return None
    return f"https://www.nowcoder.com/discuss/{m.group(1)}"


def extract_nowcoder_urls_from_html(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _DISCUSS_ID.finditer(html):
        canonical = f"https://www.nowcoder.com/discuss/{m.group(1)}"
        if canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        canonical = normalize_nowcoder_discuss_url(a["href"])
        if canonical and canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    return found


def _default_search_fetcher(query: str) -> str:
    session = build_session(extra_headers=_DEFAULT_HEADERS)
    resp = request_with_retry(
        session,
        "POST",
        _DDG_URL,
        data={"q": query},
        timeout=25,
    )
    resp.raise_for_status()
    return resp.text


def discover_nowcoder_urls(
    queries: list[str],
    *,
    max_per_query: int = 5,
    search_fetcher: Callable[[str], str] | None = None,
    request_delay: float = 1.0,
) -> tuple[list[str], dict]:
    """Search `site:nowcoder.com/discuss <query>` and return deduped discuss URLs."""
    fetcher = search_fetcher or _default_search_fetcher
    out: list[str] = []
    seen: set[str] = set()
    meta: dict = {"source": "duckduckgo", "per_query": [], "queries": []}
    for i, query in enumerate(queries):
        if i and request_delay > 0:
            time.sleep(request_delay)
        q = query.strip()
        if not q:
            continue
        search_q = f"site:nowcoder.com/discuss {q}"
        row = {"query": q, "urls": [], "error": None}
        try:
            html = fetcher(search_q)
            html = unquote(html)
            count_this_query = 0
            for url in extract_nowcoder_urls_from_html(html):
                if url in seen:
                    continue
                seen.add(url)
                out.append(url)
                row["urls"].append(url)
                count_this_query += 1
                if count_this_query >= max_per_query:
                    break
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        meta["per_query"].append(row)
        meta["queries"].append(q)
    meta["count"] = len(out)
    return out, meta
