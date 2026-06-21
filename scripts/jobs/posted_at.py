"""Parse job posted dates, filter by recency, and sort."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from scripts.jobs.connectors.bytedance import parse_bytedance_search
from scripts.jobs.http import build_session
from scripts.jobs.models import JobPosting

_DATE_FIELD_KEYS = (
    "publish_time",
    "publishTime",
    "release_time",
    "releaseTime",
    "create_time",
    "createTime",
    "created_at",
    "createdAt",
    "update_time",
    "updateTime",
    "updated_at",
    "updatedAt",
    "post_time",
    "online_time",
    "publish_date",
    "release_date",
    "posted_at",
    "postedAt",
    "gmtCreate",
    "gmtModified",
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _epoch_to_iso_date(value: int | str | float | None) -> str | None:
    if value is None:
        return None
    try:
        ts = int(value)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _string_to_iso_date(text: str) -> str | None:
    s = text.strip()
    if not s:
        return None
    if _ISO_DATE.match(s):
        return s[:10]
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def coerce_posted_at(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _epoch_to_iso_date(int(value))
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _epoch_to_iso_date(text)
    return _string_to_iso_date(text)


def parse_posted_at_from_payload(data: dict | None) -> str | None:
    if not data:
        return None
    for key in _DATE_FIELD_KEYS:
        if key in data and data[key] is not None:
            iso = coerce_posted_at(data[key])
            if iso:
                return iso
    for val in data.values():
        if isinstance(val, dict):
            iso = parse_posted_at_from_payload(val)
            if iso:
                return iso
    return None


def apply_posted_at_from_payload(job: JobPosting, data: dict | None) -> bool:
    iso = parse_posted_at_from_payload(data)
    if not iso:
        return False
    job.posted_at = iso
    return True


def infer_bytedance_portal_type(url: str) -> int:
    u = (url or "").lower()
    if "/campus/" in u:
        return 3
    return 2


def _paginate_bytedance_posted_dates(
    portal_type: int,
    *,
    recruitment_id_list: list[str] | None = None,
    max_jobs: int = 800,
) -> dict[str, str]:
    from scripts.jobs.connectors.bytedance import ByteDanceConnector

    session = build_session()
    conn = ByteDanceConnector(
        session=session,
        portal_type=portal_type,
        recruitment_id_list=recruitment_id_list or [],
    )
    csrf = conn._ensure_csrf(session)
    id_to_date: dict[str, str] = {}
    offset = 0
    while offset < max_jobs:
        limit = min(50, max_jobs - offset)
        try:
            payload = conn._search_page(session, csrf, "", offset, limit)
        except Exception:  # noqa: BLE001
            break
        batch = parse_bytedance_search(payload)
        if not batch:
            break
        for job in batch:
            if job.source_id and job.posted_at:
                id_to_date[job.source_id] = job.posted_at
        offset += len(batch)
        if len(batch) < limit:
            break
    return id_to_date


def backfill_bytedance_posted_at(
    jobs: list[JobPosting],
    queries: list[str],
    *,
    max_per_query: int = 100,
) -> int:
    """Match job-pro 字节岗位到官方 API 的 publish_time。"""
    del max_per_query  # pagination uses fixed page size
    need = [
        j
        for j in jobs
        if not j.posted_at
        and (
            j.source.startswith("job_pro:bytedance")
            or "jobs.bytedance.com" in (j.url or "")
            or j.company == "字节跳动"
        )
    ]
    if not need:
        return 0

    id_to_date: dict[str, str] = {}
    portal_configs: dict[int, list[str]] = {2: [], 3: ["201"]}
    for portal, rec_ids in portal_configs.items():
        if portal not in {infer_bytedance_portal_type(j.url or "") for j in need}:
            # still scan both portals when mixed
            pass
        id_to_date.update(
            _paginate_bytedance_posted_dates(
                portal,
                recruitment_id_list=rec_ids,
                max_jobs=800,
            )
        )

    filled = 0
    for job in need:
        iso = id_to_date.get(job.source_id)
        if iso:
            job.posted_at = iso
            filled += 1
    return filled


def _parse_posted_date(job: JobPosting) -> date | None:
    raw = (job.posted_at or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def filter_official_jobs_by_recency(
    jobs: list[JobPosting],
    *,
    window_days: int = 60,
    today: date | None = None,
    official_prefix: str = "job_pro",
) -> tuple[list[JobPosting], dict]:
    """仅过滤官网(job-pro)岗位；Boss 等聚合源保留。无发布日期的官网岗位剔除。"""
    ref = today or date.today()
    cutoff = ref - timedelta(days=window_days)
    kept: list[JobPosting] = []
    meta = {
        "window_days": window_days,
        "official_before": 0,
        "official_kept": 0,
        "official_dropped_no_date": 0,
        "official_dropped_old": 0,
    }
    for job in jobs:
        if not (job.source or "").startswith(official_prefix):
            kept.append(job)
            continue
        meta["official_before"] += 1
        posted = _parse_posted_date(job)
        if posted is None:
            meta["official_dropped_no_date"] += 1
            continue
        if posted < cutoff:
            meta["official_dropped_old"] += 1
            continue
        meta["official_kept"] += 1
        kept.append(job)
    return kept, meta


def sort_jobs_by_posted_at(jobs: list[JobPosting], *, descending: bool = True) -> list[JobPosting]:
    def key(job: JobPosting) -> tuple[int, str]:
        posted = _parse_posted_date(job)
        if posted is None:
            return (0, "")
        return (1, posted.isoformat())

    return sorted(jobs, key=key, reverse=descending)
