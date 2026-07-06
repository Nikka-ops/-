"""Discover 牛客面经 via official search API (moments with full text)."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from scripts.corpus.classify import extract_company_role
from scripts.discover.nowcoder_detail import enrich_nowcoder_text
from scripts.net.http_client import build_session
from scripts.models import RawPost
from scripts.net.retry import request_with_retry

_SEARCH_URL = "https://gw-c.nowcoder.com/api/sparta/pc/search"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.nowcoder.com/",
    "Origin": "https://www.nowcoder.com",
}
_HTML_TAG = re.compile(r"<[^>]+>")


def _epoch_ms_to_iso(value: int | str | None) -> str | None:
    if value is None:
        return None
    try:
        ts = int(value)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError, TypeError):
        return None


def _clean_moment_html(text: str) -> str:
    return _HTML_TAG.sub("", text or "").strip()


def _iter_search_payloads(rec: dict) -> list[dict]:
    """Normalize search record payloads; API sometimes returns data as list (job cards)."""
    raw = rec.get("data")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _moment_dict_from_payload(payload: dict) -> dict | None:
    moment = payload.get("momentData")
    if isinstance(moment, dict) and (moment.get("id") or moment.get("uuid")):
        return moment
    content = payload.get("contentData")
    if isinstance(content, dict) and (content.get("id") or content.get("uuid")):
        images = content.get("contentImageUrls") or []
        img_moment = [{"src": str(u)} for u in images if u]
        return {
            "id": content.get("id"),
            "uuid": content.get("uuid"),
            "title": content.get("title") or content.get("newTitle"),
            "content": content.get("content") or content.get("newContent"),
            "createdAt": content.get("createTime") or content.get("showTime"),
            "imgMoment": img_moment,
        }
    return None


def _moment_identity(moment: dict) -> str:
    return str(moment.get("id") or moment.get("uuid") or "").strip()


def moment_to_raw_post(moment: dict) -> RawPost | None:
    title = _clean_moment_html(moment.get("title") or moment.get("newTitle") or "")
    body = _clean_moment_html(moment.get("content") or moment.get("newContent") or "")
    image_urls: list[str] = []
    for item in moment.get("imgMoment") or []:
        if isinstance(item, dict) and item.get("src"):
            image_urls.append(str(item["src"]))
    moment_id = moment.get("id")
    uuid = str(moment.get("uuid") or "").strip()
    if not title and not body and not image_urls:
        return None
    if uuid:
        url = f"https://www.nowcoder.com/feed/main/detail/{uuid}"
    elif moment_id:
        url = f"https://www.nowcoder.com/feed/detail/{moment_id}"
    else:
        url = "https://www.nowcoder.com/"
    body = enrich_nowcoder_text(url, title, body)
    raw_text = f"{title}\n{body}" if title and body else title or body
    post_type = "image" if image_urls and len(body) < 40 else "mixed" if image_urls else "text"
    company, role = extract_company_role(title=title, desc=body)
    return RawPost(
        source="nowcoder",
        url=url,
        post_type=post_type,
        raw_text=raw_text,
        posted_at=_epoch_ms_to_iso(moment.get("createdAt")),
        company=company,
        role=role,
        asset_paths=image_urls,
    )


def search_nowcoder_moments(
    queries: list[str],
    *,
    max_per_query: int = 50,
    page_size: int = 30,
    request_delay: float = 0.5,
    max_pages: int = 10,
) -> tuple[list[RawPost], dict]:
    """Search 牛客并返回带正文的面经动态（不依赖 discuss 详情页 / DDG）。"""
    posts: list[RawPost] = []
    seen_ids: set[str] = set()
    meta: dict = {"queries": [], "source": "nowcoder_api", "per_query": []}
    session = build_session(extra_headers=_DEFAULT_HEADERS)

    for i, query in enumerate(queries):
        q = query.strip()
        if not q:
            continue
        if i and request_delay > 0:
            time.sleep(request_delay)
        row = {"query": q, "fetched": 0, "pages": 0, "error": None}
        count = 0
        try:
            for page in range(1, max_pages + 1):
                if count >= max_per_query:
                    break
                resp = request_with_retry(
                    session,
                    "POST",
                    _SEARCH_URL,
                    json={
                        "query": q.replace(" ", ""),
                        "type": "all",
                        "page": page,
                        "pageSize": page_size,
                    },
                    timeout=25,
                )
                resp.raise_for_status()
                payload = resp.json()
                if not payload.get("success"):
                    row["error"] = payload.get("msg") or "search failed"
                    break
                data = payload.get("data")
                if isinstance(data, list):
                    records = []
                    for item in data:
                        if isinstance(item, dict):
                            nested = item.get("records")
                            records.extend(nested if isinstance(nested, list) else [item])
                elif isinstance(data, dict):
                    records = data.get("records") or []
                else:
                    records = []
                row["pages"] = page
                row["total_hits"] = data.get("total") if isinstance(data, dict) else len(records)
                if not records:
                    break
                page_added = 0
                for rec in records:
                    for search_payload in _iter_search_payloads(rec):
                        moment = _moment_dict_from_payload(search_payload)
                        if not moment:
                            continue
                        moment_id = _moment_identity(moment)
                        if not moment_id or moment_id in seen_ids:
                            continue
                        post = moment_to_raw_post(moment)
                        if not post:
                            continue
                        seen_ids.add(moment_id)
                        posts.append(post)
                        count += 1
                        page_added += 1
                        if count >= max_per_query:
                            break
                    if count >= max_per_query:
                        break
                if page_added == 0 or count >= max_per_query:
                    break
                if request_delay > 0:
                    time.sleep(request_delay * 0.5)
            row["fetched"] = count
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        meta["per_query"].append(row)
        meta["queries"].append(q)

    meta["count"] = len(posts)
    return posts, meta
