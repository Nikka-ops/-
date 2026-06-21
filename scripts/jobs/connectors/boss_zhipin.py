"""Boss直聘职位搜索 — 需要浏览器 Cookie（反爬）。"""
from __future__ import annotations

import os
from collections.abc import Callable
from urllib.parse import quote

from scripts.config import boss_zhipin_cookie
from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.http import build_session
from scripts.jobs.models import JobPosting

# 常见城市 code（Boss 直聘）；默认北京
_CITY_CODES: dict[str, str] = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
    "苏州": "101190400",
}


_DETAIL_API = "https://www.zhipin.com/wapi/zpgeek/job/detail.json"


def parse_boss_detail(payload: dict) -> str:
    """Parse Boss直聘 detail.json response into job description text."""
    if payload.get("code") != 0:
        return ""
    zp = payload.get("zpData") or {}
    job = zp.get("jobInfo") or {}
    parts: list[str] = []
    if job.get("postDescription"):
        parts.append(str(job["postDescription"]))
    if job.get("jobDesc"):
        parts.append(str(job["jobDesc"]))
    return "\n".join(parts).strip()


def apply_boss_detail(job: JobPosting, payload: dict) -> None:
    desc = parse_boss_detail(payload)
    if desc:
        job.description = desc
        if job.extra:
            job.extra["needs_detail_fetch"] = False


def _resolve_city_code(city: str | None) -> str:
    if not city:
        return _CITY_CODES["北京"]
    city = city.strip()
    if city.isdigit():
        return city
    return _CITY_CODES.get(city, _CITY_CODES["北京"])


def parse_boss_joblist(payload: dict, *, fetch_detail: bool = False) -> list[JobPosting]:
    """Parse Boss直聘 joblist.json response."""
    if payload.get("code") != 0:
        return []
    zp = payload.get("zpData") or {}
    job_list = zp.get("jobList") or []
    jobs: list[JobPosting] = []
    for item in job_list:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("encryptJobId") or item.get("jobId") or "")
        if not job_id:
            continue
        title = str(item.get("jobName") or item.get("name") or "").strip()
        company = str(item.get("brandName") or item.get("companyName") or "未知公司").strip()
        city_name = str(item.get("cityName") or item.get("city") or "").strip()
        salary = str(item.get("salaryDesc") or item.get("salary") or "").strip()
        experience = str(item.get("jobExperience") or "").strip()
        education = str(item.get("jobDegree") or "").strip()
        tags = [str(t) for t in (item.get("jobLabels") or []) if t]
        skills = item.get("skills") or []
        if isinstance(skills, list):
            tags.extend(str(s) for s in skills if s)
        lid = str(item.get("lid") or "")
        url = f"https://www.zhipin.com/job_detail/{quote(job_id)}.html"
        if lid:
            url += f"?lid={quote(lid)}"
        desc_parts = []
        if item.get("jobDesc"):
            desc_parts.append(str(item["jobDesc"]))
        if item.get("postDescription"):
            desc_parts.append(str(item["postDescription"]))
        description = "\n".join(desc_parts).strip()
        jobs.append(
            JobPosting(
                source="boss_zhipin",
                source_id=job_id,
                url=url,
                title=title,
                company=company,
                description=description,
                role=title,
                city=city_name or None,
                salary=salary or None,
                experience=experience or None,
                education=education or None,
                status="open",
                tags=tags,
                extra={
                    "lid": lid,
                    "boss_name": item.get("bossName"),
                    "boss_title": item.get("bossTitle"),
                    "security_id": item.get("securityId"),
                    "needs_detail_fetch": not description and fetch_detail,
                },
            )
        )
    return jobs


class BossZhipinConnector(JobConnector):
    name = "boss_zhipin"
    label = "Boss直聘"
    company = ""

    def __init__(
        self,
        *,
        cookie: str | None = None,
        session=None,
        fetcher: Callable[[str, dict], dict] | None = None,
        prefer_cdp: bool = False,
        cdp_port: int | None = None,
    ) -> None:
        self._cookie = cookie or boss_zhipin_cookie()
        self._session = session
        self._fetcher = fetcher
        self._prefer_cdp = prefer_cdp
        self._cdp_port = cdp_port

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        from scripts.jobs.connectors.boss_cdp import BossCdpConnector

        if self._prefer_cdp or not self._cookie:
            cdp = BossCdpConnector(port=self._cdp_port)
            cdp_result = cdp.search(queries, city=city, max_per_query=max_per_query)
            if cdp_result.status == "ok" and cdp_result.jobs:
                return cdp_result
            if not self._cookie:
                if cdp_result.status == "degraded":
                    cdp_result.message += (
                        "；或配置 BOSS_ZHIPIN_COOKIE，见 docs/setup/boss-zhipin-cookie.md"
                    )
                return cdp_result

        cookie_result = self._search_with_cookie(queries, city=city, max_per_query=max_per_query)
        if cookie_result.status == "ok" and cookie_result.jobs:
            return cookie_result
        if cookie_result.status == "degraded":
            from scripts.jobs.connectors.boss_cdp import BossCdpConnector

            cdp = BossCdpConnector(port=self._cdp_port)
            cdp_result = cdp.search(queries, city=city, max_per_query=max_per_query)
            if cdp_result.status == "ok" and cdp_result.jobs:
                return cdp_result
        return cookie_result

    def _search_with_cookie(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        if not self._cookie:
            return JobSearchResult.degraded(
                self.name,
                "未配置 Cookie。导出浏览器 Cookie 后设置 BOSS_ZHIPIN_COOKIE 或 INTERVIEWRADAR_BOSS_COOKIE",
            )
        city_code = _resolve_city_code(city)
        session = self._session or build_session()
        session.headers.update(
            {
                "Referer": "https://www.zhipin.com/",
                "Cookie": self._cookie,
                "Accept": "application/json",
            }
        )
        all_jobs: list[JobPosting] = []
        seen: set[str] = set()
        errors: list[str] = []

        for query in queries:
            if not query.strip():
                continue
            try:
                batch = self._fetch_all_pages(session, query.strip(), city_code, max_per_query)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query}: {exc}")
                continue
            code = batch.get("code")
            if code != 0:
                msg = str(batch.get("message") or batch.get("zpData") or code)
                if code == 37 or "异常" in msg or "登录" in msg:
                    return JobSearchResult.degraded(
                        self.name,
                        f"Cookie 失效或触发反爬: {msg}。请重新导出 Cookie。",
                    )
                errors.append(f"{query}: {msg}")
                continue
            for job in parse_boss_joblist(batch):
                fp = job.fingerprint()
                if fp in seen:
                    continue
                seen.add(fp)
                all_jobs.append(job)

        self._enrich_missing_descriptions(session, all_jobs)

        if not all_jobs and errors:
            return JobSearchResult.degraded(self.name, "; ".join(errors))
        msg = f"{len(all_jobs)} jobs"
        if errors:
            msg += f" (warnings: {len(errors)})"
        return JobSearchResult.ok(all_jobs, msg)

    def _enrich_missing_descriptions(self, session, jobs: list[JobPosting]) -> None:
        for job in jobs:
            if job.description:
                continue
            security_id = str((job.extra or {}).get("security_id") or "").strip()
            if not security_id:
                continue
            try:
                if self._fetcher:
                    payload = self._fetcher(_DETAIL_API, {"securityId": security_id})
                else:
                    resp = session.get(
                        _DETAIL_API,
                        params={"securityId": security_id},
                        timeout=20,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                apply_boss_detail(job, payload)
            except Exception:  # noqa: BLE001
                continue

    def _fetch_all_pages(
        self,
        session,
        query: str,
        city_code: str,
        limit: int,
        *,
        max_pages: int = 8,
    ) -> dict:
        merged_list: list = []
        last_payload: dict = {"code": -1, "message": "no pages"}
        for page in range(1, max_pages + 1):
            if len(merged_list) >= limit:
                break
            page_size = min(30, limit - len(merged_list))
            payload = self._fetch_page(session, query, city_code, page, page_size)
            last_payload = payload
            code = payload.get("code")
            if code != 0:
                return payload
            zp = payload.get("zpData") or {}
            batch = zp.get("jobList") or []
            merged_list.extend(batch)
            if not batch or not zp.get("hasMore"):
                break
        if last_payload.get("code") != 0:
            return last_payload
        return {
            "code": 0,
            "message": last_payload.get("message"),
            "zpData": {
                "jobList": merged_list[:limit],
                "hasMore": False,
            },
        }

    def _fetch_page(
        self,
        session,
        query: str,
        city_code: str,
        page: int,
        page_size: int,
    ) -> dict:
        params = {
            "scene": "1",
            "query": query,
            "city": city_code,
            "page": str(page),
            "pageSize": str(min(page_size, 30)),
        }
        if self._fetcher:
            return self._fetcher(
                "https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
                params,
            )
        resp = session.get(
            "https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
