"""Job JD fetch module."""
from scripts.jobs.models import JobPosting
from scripts.jobs.service import (
    catalog_job_sources,
    fetch_jobs,
    fetch_jobs_multi,
    get_job_snapshot,
    list_job_snapshots,
    JobFetchConfig,
    JobFetchResult,
)

__all__ = [
    "JobPosting",
    "JobFetchConfig",
    "JobFetchResult",
    "fetch_jobs",
    "fetch_jobs_multi",
    "list_job_snapshots",
    "get_job_snapshot",
    "catalog_job_sources",
]
