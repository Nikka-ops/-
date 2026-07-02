"""网易招聘 — 通过 job-pro CLI。"""
from __future__ import annotations

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.connectors.job_pro import JobProConnector


class NetEaseConnector(JobConnector):
    name = "netease"
    label = "网易招聘"
    company = "网易"

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 50,
    ) -> JobSearchResult:
        delegate = JobProConnector(company_keys=["netease"], scope="social")
        result = delegate.search(queries, city=city, max_per_query=max_per_query)
        for job in result.jobs:
            job.source = "netease"
            job.company = "网易"
        return JobSearchResult(jobs=result.jobs, status=result.status, message=result.message)
