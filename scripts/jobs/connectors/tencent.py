"""腾讯招聘官网 — 公开 REST API，无需 Cookie。"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.http import build_session
from scripts.jobs.models import JobPosting

_QUERY_URL = "https://careers.tencent.com/tencentcareer/api/post/Query"
_DETAIL_BASE = "https://careers.tencent.com/jobdesc.html?postId={post_id}"

_CATEGORY_DATA = "2"   # 技术类 category
_AREA = "cn"


def _parse_post(item: dict) -> JobPosting | None:
    if not isinstance(item, dict):
        return None
    post_id = str(item.get("PostId") or "").strip()
    title = str(item.get("RecruitPostName") or "").strip()
    if not post_id or not title:
        return None
    city_raw = item.get("LocationName") or item.get("LocationIdName") or ""
    city = str(city_raw).strip() or None
    desc_parts: list[str] = []
    for key in ("Responsibility", "Requirement"):
        val = str(item.get(key) or "").strip()
        if val:
            desc_parts.append(val)
    description = "\n\n".join(desc_parts)

    bg = str(item.get("BGName") or "").strip()
    category = str(item.get("CategoryName") or "").strip()
    tags: list[str] = [t for t in [bg, category] if t]

    posted_at = None
    for key in ("LastUpdateTime", "CreateTime"):
        raw = str(item.get(key) or "").strip()
        if raw:
            try:
                posted_at = datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
                break
            except (ValueError, TypeError):
                pass

    return JobPosting(
        source="tencent",
        source_id=post_id,
        url=_DETAIL_BASE.format(post_id=post_id),
        title=title,
        company="腾讯",
        description=description,
        role=title,
        city=city,
        posted_at=posted_at,
        status="open",
        tags=tags,
        extra={"bg": bg},
    )


class TencentConnector(JobConnector):
    name = "tencent"
    label = "腾讯招聘"
    company = "腾讯"

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 50,
    ) -> JobSearchResult:
        session = build_session()
        session.headers.update({
            "Referer": "https://careers.tencent.com/",
            "Origin": "https://careers.tencent.com",
        })
        all_jobs: list[JobPosting] = []
        seen: set[str] = set()
        errors: list[str] = []

        query_list = [q.strip() for q in queries if q.strip()] or [""]
        for query in query_list[:8]:
            try:
                batch = self._fetch_all(session, query, max_per_query)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query}: {exc}")
                continue
            for job in batch:
                fp = job.fingerprint()
                if fp not in seen:
                    seen.add(fp)
                    all_jobs.append(job)

        if not all_jobs and errors:
            return JobSearchResult.degraded(self.name, "; ".join(errors))
        msg = f"{len(all_jobs)} jobs"
        if errors:
            msg += f" ({len(errors)} errors)"
        return JobSearchResult.ok(all_jobs, msg)

    def _fetch_all(self, session, keyword: str, limit: int) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        page_size = min(20, limit)
        page = 1
        while len(jobs) < limit:
            params = {
                "timestamp": str(int(time.time() * 1000)),
                "countryId": "",
                "cityId": "",
                "bgIds": "",
                "productId": "",
                "categoryId": "",
                "parentCategoryId": "",
                "attrId": "",
                "keyword": keyword,
                "pageIndex": str(page),
                "pageSize": str(page_size),
                "language": "zh-cn",
                "area": _AREA,
            }
            resp = session.get(_QUERY_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            code = data.get("Code")
            if code not in ("SUCCESS", 200, "200"):
                break
            posts = (data.get("Data") or {}).get("Posts") or []
            for item in posts:
                job = _parse_post(item)
                if job:
                    jobs.append(job)
            total = int((data.get("Data") or {}).get("Count") or 0)
            if not posts or len(jobs) >= min(limit, total):
                break
            page += 1
        return jobs[:limit]
