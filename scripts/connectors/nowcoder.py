"""NowCoder discuss-page connector.

Current selector assumptions (verified 2026-06-18 against live HTML):
- Title:   <div class="content-post-title"><h1>...</h1></div>
- Content: <div class="nc-post-content"> (2026+) or legacy <div class="nc-slate-editor-content">
- Date:    "createTime": <epoch_ms> in __INITIAL_STATE__ / embedded JS blob.

If parsing returns empty title AND empty content for every URL, the connector
degrades with a "selector" message — NowCoder almost certainly updated their
schema. Inspect the live HTML and update selectors above.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scripts.connectors.base import Connector, SearchResult
from scripts.corpus.classify import extract_company_role
from scripts.net.http_client import build_session
from scripts.net.retry import request_with_retry
from scripts.models import RawPost

_CREATE_TIME = re.compile(r'"createTime"\s*:\s*(\d{10,13})')
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.nowcoder.com/",
}


def _parse_create_time(html: str) -> str | None:
    m = _CREATE_TIME.search(html)
    if not m:
        return None
    try:
        ts = int(m.group(1))
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError):
        return None


def _extract_body(soup: BeautifulSoup) -> str:
    for selector in ("div.nc-post-content", "div.nc-slate-editor-content"):
        el = soup.select_one(selector)
        if not el:
            continue
        blocks: list[str] = []
        for node in el.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "div"]):
            # skip nested duplicates: only direct meaningful blocks
            if node.name == "div" and node.find(["p", "li", "h2", "h3"]):
                continue
            text = node.get_text("\n", strip=True)
            if text and len(text) >= 2:
                blocks.append(text)
        if blocks:
            # dedupe consecutive identical lines
            out: list[str] = []
            for b in blocks:
                if not out or out[-1] != b:
                    out.append(b)
            return "\n\n".join(out)
        text = el.get_text("\n", strip=True)
        if text:
            return text
    return ""


def parse_nowcoder_post(html: str, url: str) -> RawPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("div.content-post-title h1")
    title = title_el.get_text(strip=True) if title_el else ""

    body = _extract_body(soup)
    posted_at = _parse_create_time(html)

    if title and body:
        raw_text = f"{title}\n{body}"
    else:
        raw_text = title or body
    company, role = extract_company_role(title=title)
    return RawPost(
        source="nowcoder",
        url=url,
        post_type="text",
        raw_text=raw_text,
        posted_at=posted_at,
        company=company,
        role=role,
    )


def _default_fetcher(url: str) -> str:
    session = build_session(extra_headers=_DEFAULT_HEADERS)
    resp = request_with_retry(session, "GET", url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _looks_like_waf_page(html: str) -> bool:
    return "aliyun_waf" in html or len(html) < 20_000


def _fetch_post(url: str, fetcher: Callable[[str], str]) -> RawPost:
    html = fetcher(url)
    post = parse_nowcoder_post(html, url)
    # Anti-bot often returns a stub page with createTime but no body; retry once.
    if len(post.raw_text) < 80 and _parse_create_time(html) and not _looks_like_waf_page(html):
        time.sleep(1.5)
        post = parse_nowcoder_post(fetcher(url), url)
    return post


class NowCoderConnector(Connector):
    name = "nowcoder"

    def __init__(
        self,
        post_urls: list[str],
        fetcher: Callable[[str], str] | None = None,
        request_delay: float = 1.0,
    ):
        self.post_urls = post_urls
        self.fetcher = fetcher or _default_fetcher
        self.request_delay = request_delay

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        errors: list[str] = []
        for i, url in enumerate(self.post_urls):
            if i and self.request_delay > 0:
                time.sleep(self.request_delay)
            try:
                posts.append(_fetch_post(url, self.fetcher))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")

        if not posts and errors:
            return SearchResult.degraded(
                self.name,
                f"全部 URL 抓取失败; 首条: {errors[0]}; 牛客需要登录请提供 cookie 或手动粘贴链接",
            )

        empties = [p for p in posts if not p.raw_text]
        if posts and len(empties) == len(posts):
            return SearchResult.degraded(
                self.name,
                "解析后的标题和正文都为空,NowCoder HTML 选择器可能已漂移;"
                "请对照 scripts/connectors/nowcoder.py 顶部注释更新 selectors",
            )

        if posts and len(empties) / len(posts) >= 0.5:
            good = [p for p in posts if p.raw_text]
            msg = (
                f"[{self.name}] {len(empties)}/{len(posts)} 帖正文为空"
                "(疑似 anti-bot 间歇响应:createTime 在但正文 div 缺失);"
                f"仅保留 {len(good)} 帖成功内容,建议加 cookie 或稍后重试"
            )
            if errors:
                msg += f"; {len(errors)} URL 失败"
            return SearchResult(
                posts=good,
                status="degraded",
                message=msg,
            )

        if errors:
            return SearchResult(
                posts=posts,
                status="degraded",
                message=f"{len(posts)} posts; {len(errors)} URL 失败",
            )

        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
