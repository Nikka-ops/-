"""小米招聘 — 通过 job-pro CLI。"""
from __future__ import annotations

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.connectors.job_pro import JobProConnector


class XiaomiConnector(JobConnector):
    name = "xiaomi"
    label = "小米招聘"
    company = "小米"

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 50,
    ) -> JobSearchResult:
        delegate = JobProConnector(company_keys=["xiaomi"], scope="social")
        result = delegate.search(queries, city=city, max_per_query=max_per_query)
        for job in result.jobs:
            job.source = "xiaomi"
            job.company = "小米"
        return JobSearchResult(jobs=result.jobs, status=result.status, message=result.message)
