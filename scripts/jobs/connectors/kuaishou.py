"""快手招聘 — 通过 job-pro CLI。"""
from __future__ import annotations

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.connectors.job_pro import JobProConnector


class KuaishouConnector(JobConnector):
    name = "kuaishou"
    label = "快手招聘"
    company = "快手"

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 50,
    ) -> JobSearchResult:
        delegate = JobProConnector(company_keys=["kuaishou"], scope="social")
        result = delegate.search(queries, city=city, max_per_query=max_per_query)
        for job in result.jobs:
            job.source = "kuaishou"
            job.company = "快手"
        return JobSearchResult(jobs=result.jobs, status=result.status, message=result.message)
