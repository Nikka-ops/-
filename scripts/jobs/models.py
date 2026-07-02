"""Job posting (JD) models — separate from interview post corpus."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields


@dataclass
class JobPosting:
    source: str
    source_id: str
    url: str
    title: str
    company: str
    description: str = ""
    role: str | None = None
    city: str | None = None
    salary: str | None = None
    experience: str | None = None
    education: str | None = None
    posted_at: str | None = None  # ISO date when first published
    updated_at: str | None = None
    status: str = "open"  # open | closed | unknown
    is_new: bool = False  # first seen in latest fetch vs prior cache
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from scripts.corpus.company_normalize import normalize_company_name

        d = asdict(self)
        if d.get("company"):
            d["company"] = normalize_company_name(str(d["company"])) or d["company"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JobPosting":
        data = dict(d)
        data.setdefault("description", "")
        data.setdefault("status", "open")
        data.setdefault("is_new", False)
        data.setdefault("tags", [])
        data.setdefault("extra", {})
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def fingerprint(self) -> str:
        return f"{self.source}:{self.source_id}"
