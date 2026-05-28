import re
from collections.abc import Callable

import requests

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_KEYWORDS = ("介绍", "说明", "区别", "原理", "什么是", "如何", "为什么", "解释")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^(?:[-*]|\d+\.)\s+(.*)$")


def _is_question_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.endswith("?") or t.endswith("？"):
        return True
    return any(k in t for k in _KEYWORDS)


def extract_posts_from_markdown(md_text: str, url: str) -> list[RawPost]:
    posts: list[RawPost] = []
    for line in md_text.splitlines():
        m = _HEADING.match(line) or _BULLET.match(line)
        candidate = m.group(1).strip() if m else line.strip()
        if _is_question_like(candidate):
            posts.append(RawPost(source="github", url=url, post_type="text", raw_text=candidate))
    return posts


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class GithubConnector(Connector):
    name = "github"

    def __init__(self, repo_raw_urls: list[str], fetcher: Callable[[str], str] | None = None):
        self.repo_raw_urls = repo_raw_urls
        self.fetcher = fetcher or _default_fetcher

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        try:
            for url in self.repo_raw_urls:
                posts.extend(extract_posts_from_markdown(self.fetcher(url), url))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(self.name, f"fetch failed: {exc}")
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
