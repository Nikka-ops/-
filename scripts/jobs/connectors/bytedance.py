"""字节跳动招聘站 — 公开 API（CSRF session）。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import unquote

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.http import build_session
from scripts.jobs.models import JobPosting

_CSRF_URL = "https://jobs.bytedance.com/api/v1/csrf/token"
_SEARCH_URL = "https://jobs.bytedance.com/api/v1/search/job/posts"
_DETAIL_BASE = "https://jobs.bytedance.com/experienced/position"


def parse_bytedance_job(item: dict) -> JobPosting | None:
    if not isinstance(item, dict):
        return None
    job_id = str(item.get("id") or "")
    title = str(item.get("title") or "").strip()
    if not job_id or not title:
        return None
    city_info = item.get("city_info") or {}
    city = str(city_info.get("name") or city_info.get("i18n_name") or "").strip() or None
    desc = str(item.get("description") or "").strip()
    req = str(item.get("requirement") or "").strip()
    description = desc
    if req:
        description = f"{desc}\n\n任职要求:\n{req}".strip()
    recruit = item.get("recruit_type") or {}
    recruit_name = str(recruit.get("name") or recruit.get("i18n_name") or "").strip()
    parent = recruit.get("parent") or {}
    channel = str(parent.get("name") or parent.get("i18n_name") or "").strip()
    tags: list[str] = []
    if channel:
        tags.append(channel)
    if recruit_name:
        tags.append(recruit_name)
    cat = item.get("job_category") or {}
    if cat.get("name"):
        tags.append(str(cat["name"]))
    posted_at = None
    publish = item.get("publish_time")
    if publish:
        try:
            ts = int(publish)
            if ts > 10_000_000_000:
                ts //= 1000
            posted_at = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            posted_at = None
    code = str(item.get("code") or "").strip()
    url = f"{_DETAIL_BASE}/{job_id}/detail"
    if code:
        url += f"?code={code}"
    return JobPosting(
        source="bytedance",
        source_id=job_id,
        url=url,
        title=title,
        company="字节跳动",
        description=description,
        role=title,
        city=city,
        posted_at=posted_at,
        status="open",
        tags=tags,
        extra={"job_code": code, "department": item.get("department_id")},
    )


def parse_bytedance_search(payload: dict) -> list[JobPosting]:
    if payload.get("code") != 0:
        return []
    data = payload.get("data") or {}
    raw_list = data.get("job_post_list") or []
    jobs: list[JobPosting] = []
    for item in raw_list:
        job = parse_bytedance_job(item)
        if job:
            jobs.append(job)
    return jobs


class ByteDanceConnector(JobConnector):
    name = "bytedance"
    label = "字节跳动招聘"
    company = "字节跳动"

    def __init__(
        self,
        *,
        session=None,
        portal_type: int = 2,
        recruitment_id_list: list[str] | None = None,
        fetcher: Callable[[str, dict], dict] | None = None,
    ) -> None:
        self._session = session
        self._portal_type = portal_type
        self._recruitment_id_list = list(recruitment_id_list or [])
        self._fetcher = fetcher

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        del city  # location filter not wired yet
        session = self._session or build_session()
        try:
            csrf = self._ensure_csrf(session)
        except Exception as exc:  # noqa: BLE001
            return JobSearchResult.degraded(self.name, f"CSRF 失败: {exc}")

        all_jobs: list[JobPosting] = []
        seen: set[str] = set()
        query_list = [q.strip() for q in queries if q.strip()]
        if not query_list:
            query_list = [""]

        for query in query_list:
            offset = 0
            page_size = min(max_per_query, 50)
            while offset < max_per_query:
                limit = min(page_size, max_per_query - offset)
                try:
                    payload = self._search_page(session, csrf, query, offset, limit)
                except Exception as exc:  # noqa: BLE001
                    return JobSearchResult.degraded(self.name, str(exc))
                batch = parse_bytedance_search(payload)
                if not batch:
                    break
                for job in batch:
                    fp = job.fingerprint()
                    if fp in seen:
                        continue
                    seen.add(fp)
                    all_jobs.append(job)
                offset += len(batch)
                if len(batch) < limit:
                    break

        return JobSearchResult.ok(all_jobs)

    def _ensure_csrf(self, session) -> str:
        resp = session.post(
            _CSRF_URL,
            headers={
                "Origin": "https://jobs.bytedance.com",
                "Referer": "https://jobs.bytedance.com/experienced/position",
            },
            timeout=20,
        )
        resp.raise_for_status()
        token = session.cookies.get("atsx-csrf-token")
        if not token:
            raise RuntimeError("missing atsx-csrf-token cookie")
        return unquote(token)

    def _search_page(self, session, csrf: str, keyword: str, offset: int, limit: int) -> dict:
        headers = {
            "Accept": "application/json",
            "Origin": "https://jobs.bytedance.com",
            "Referer": "https://jobs.bytedance.com/experienced/position",
            "x-csrf-token": csrf,
        }
        body = {
            "keyword": keyword,
            "limit": limit,
            "offset": offset,
            "portal_entrance": 1,
            "portal_type": self._portal_type,
            "job_category_id_list": [],
            "location_code_list": [],
            "recruitment_id_list": list(self._recruitment_id_list),
            "subject_id_list": [],
        }
        if self._fetcher:
            return self._fetcher(_SEARCH_URL, body)
        resp = session.post(_SEARCH_URL, headers=headers, json=body, timeout=25)
        resp.raise_for_status()
        return resp.json()
