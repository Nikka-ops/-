"""补全缺失的岗位介绍正文（job-pro detail / Boss CDP detail）。"""
from __future__ import annotations

import time

from scripts.config import boss_cdp_port
from scripts.jobs.models import JobPosting
from scripts.jobs.posted_at import apply_posted_at_from_payload, parse_posted_at_from_payload


def _apply_job_pro_detail(job: JobPosting, detail: dict) -> bool:
    desc = str(detail.get("description") or "").strip()
    req = str(detail.get("requirements") or detail.get("requirement") or "").strip()
    if desc and req:
        job.description = f"{desc}\n\n任职要求:\n{req}"
    else:
        job.description = desc or req
    apply_posted_at_from_payload(job, detail)
    pos_date = parse_posted_at_from_payload(
        {k: detail.get(k) for k in ("position", "post", "data") if detail.get(k)}
    )
    if pos_date and not job.posted_at:
        job.posted_at = pos_date
    return bool(job.description.strip())


# 薄包装连接器的 source 标签 → 对应 job-pro company key
_WRAPPER_SOURCE_TO_KEY: dict[str, str] = {
    "meituan":  "meituan",
    "netease":  "netease",
    "xiaomi":   "xiaomi",
    "kuaishou": "kuaishou",
}


def enrich_job_pro_description(job: JobPosting) -> bool:
    if (job.description or "").strip():
        return False
    src = job.source or ""
    company_key = str((job.extra or {}).get("job_pro_key") or "")
    if not company_key:
        if src.startswith("job_pro"):
            parts = src.split(":")
            company_key = parts[-1] if len(parts) > 1 else ""
        elif src in _WRAPPER_SOURCE_TO_KEY:
            company_key = _WRAPPER_SOURCE_TO_KEY[src]
    if not company_key or not src.startswith("job_pro") and src not in _WRAPPER_SOURCE_TO_KEY:
        return False
    if not job.source_id:
        return False
    from scripts.jobs.connectors.job_pro import JobProConnector

    conn = JobProConnector(company_keys=[company_key], with_details=True)
    detail = conn._fetch_detail(company_key, job.source_id)
    if not detail:
        return False
    return _apply_job_pro_detail(job, detail)


def enrich_boss_description(job: JobPosting, *, port: int | None = None) -> bool:
    if (job.description or "").strip():
        return False
    if job.source not in ("boss_cdp", "boss_zhipin"):
        return False
    security_id = str((job.extra or {}).get("security_id") or "").strip()
    if not security_id:
        return False
    from scripts.jobs.connectors.boss_cdp import BossCdpConnector
    from scripts.jobs.cdp_client import CdpError, cdp_port_open, open_zhipin_page
    from scripts.jobs.connectors.boss_zhipin import apply_boss_detail

    cdp_port = port if port is not None else boss_cdp_port()
    if not cdp_port_open(cdp_port):
        return False
    try:
        page_ws = open_zhipin_page(cdp_port)
    except CdpError:
        return False
    conn = BossCdpConnector(port=cdp_port, with_details=False)
    delays = [0.0, 2.0, 4.0]
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            payload = conn._fetch_detail_via_cdp(page_ws, security_id)
        except Exception:  # noqa: BLE001
            continue
        code = payload.get("code")
        if code == 37:
            continue
        apply_boss_detail(job, payload)
        if job.description.strip():
            return True
    return False


def enrich_job_description(job: JobPosting, *, boss_port: int | None = None) -> bool:
    """补全单条岗位正文，返回是否新写入 description。"""
    if (job.description or "").strip():
        return False
    if job.source.startswith("job_pro") or job.source in _WRAPPER_SOURCE_TO_KEY:
        return enrich_job_pro_description(job)
    if job.source in ("boss_cdp", "boss_zhipin"):
        return enrich_boss_description(job, port=boss_port)
    return False


def enrich_jobs_descriptions(
    jobs: list[JobPosting],
    *,
    boss_port: int | None = None,
    boss_delay: float = 1.0,
    max_enrich: int = 120,
    skip_boss_bulk: bool = True,
) -> int:
    """批量补全缺失正文；Boss 批量拉取时默认跳过（点开岗位再懒加载）。"""
    enriched = 0
    port = boss_port if boss_port is not None else boss_cdp_port()
    for job in jobs:
        if enriched >= max_enrich:
            break
        if (job.description or "").strip():
            continue
        if job.source.startswith("job_pro") or job.source in _WRAPPER_SOURCE_TO_KEY:
            if enrich_job_pro_description(job):
                enriched += 1
        elif job.source in ("boss_cdp", "boss_zhipin"):
            if skip_boss_bulk:
                continue
            if enrich_boss_description(job, port=port):
                enriched += 1
            time.sleep(boss_delay)
    return enriched
