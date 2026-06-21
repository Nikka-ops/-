"""Base contract for job-board connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from scripts.jobs.models import JobPosting


@dataclass
class JobSearchResult:
    jobs: list[JobPosting] = field(default_factory=list)
    status: str = "ok"  # ok | degraded | error
    message: str = ""

    @classmethod
    def degraded(cls, source: str, message: str) -> "JobSearchResult":
        return cls(jobs=[], status="degraded", message=f"[{source}] {message}")

    @classmethod
    def ok(cls, jobs: list[JobPosting], message: str = "") -> "JobSearchResult":
        return cls(jobs=jobs, status="ok", message=message or f"{len(jobs)} jobs")


class JobConnector(ABC):
    name: str = "base"
    label: str = "未知来源"
    company: str = ""

    @abstractmethod
    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        raise NotImplementedError

    def to_source_meta(self) -> dict:
        return {
            "id": self.name,
            "label": self.label,
            "company": self.company,
        }
