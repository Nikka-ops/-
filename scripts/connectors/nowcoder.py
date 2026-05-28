import re
from collections.abc import Callable

import requests
from bs4 import BeautifulSoup

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_nowcoder_post(html: str, url: str) -> RawPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(".post-title")
    title = title_el.get_text(strip=True) if title_el else ""

    date_el = soup.select_one(".post-date")
    posted_at = None
    if date_el:
        m = _ISO_DATE.search(date_el.get_text(strip=True))
        if m:
            posted_at = m.group(0)

    content_el = soup.select_one(".post-content")
    if content_el:
        paras = [p.get_text(strip=True) for p in content_el.find_all("p")]
        body = "\n".join(p for p in paras if p)
    else:
        body = ""

    raw_text = (title + "\n" + body).strip() if title else body.strip()
    return RawPost(
        source="nowcoder",
        url=url,
        post_type="text",
        raw_text=raw_text,
        posted_at=posted_at,
    )


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class NowCoderConnector(Connector):
    name = "nowcoder"

    def __init__(self, post_urls: list[str], fetcher: Callable[[str], str] | None = None):
        self.post_urls = post_urls
        self.fetcher = fetcher or _default_fetcher

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        try:
            for url in self.post_urls:
                posts.append(parse_nowcoder_post(self.fetcher(url), url))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"fetch failed ({exc}); 牛客需要登录，请提供 cookie 或手动粘贴帖子链接/内容",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
