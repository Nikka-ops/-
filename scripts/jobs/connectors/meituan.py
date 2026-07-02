"""美团招聘 — 通过 job-pro CLI（官网需登录态，job-pro 已处理）。"""
from __future__ import annotations

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.connectors.job_pro import JobProConnector


class MeituanConnector(JobConnector):
    """Thin wrapper: delegates to job-pro with 'meituan' key."""

    name = "meituan"
    label = "美团招聘"
    company = "美团"

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 50,
    ) -> JobSearchResult:
        delegate = JobProConnector(company_keys=["meituan"], scope="social")
        result = delegate.search(queries, city=city, max_per_query=max_per_query)
        # Re-label source
        for job in result.jobs:
            job.source = "meituan"
            job.company = "美团"
        return JobSearchResult(jobs=result.jobs, status=result.status, message=result.message)
