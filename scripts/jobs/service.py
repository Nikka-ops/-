"""Orchestrate multi-source JD fetch."""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.config import banks_dir
from scripts.corpus.bank_cache import banks_matching_role, load_cached_raw_posts
from scripts.corpus.classify import classify_search_queries
from scripts.corpus.tech_roles import canonical_role_id, get_tech_role, resolve_role_label
from scripts.jobs.interview_link import attach_interview_context
from scripts.jobs.connectors.registry import (
    build_connector,
    list_job_sources,
    normalize_company_name,
    resolve_connector_ids,
)
from scripts.jobs.connectors.job_pro import resolve_job_pro_keys
from scripts.jobs.enrich import enrich_job_description, enrich_jobs_descriptions
from scripts.jobs.posted_at import (
    backfill_bytedance_posted_at,
    filter_official_jobs_by_recency,
    sort_jobs_by_posted_at,
)
from scripts.jobs.models import JobPosting
from scripts.jobs.store import (
    jobs_snapshot_slug,
    list_snapshots,
    load_snapshot,
    patch_job_description,
    write_snapshot,
)


@dataclass
class JobFetchConfig:
    role: str = ""
    role_id: str = ""
    companies: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    max_per_query: int = 100
    include_aggregators: bool = True
    use_job_pro: bool = True
    job_pro_scope: str = "social"
    job_pro_details: bool = True
    job_recency_days: int = 60
    boss_cdp: bool = False
    skip_interview_discover: bool = True
    cache_dir: str = ""


_DEFAULT_JOB_PRO_KEYS = [
    "bytedance",
    "tencent",
    "alibaba",
    "meituan",
    "baidu",
    "jd",
    "pdd",
    "kuaishou",
    "netease",
    "didi",
    "bilibili",
    "xiaohongshu",
    "huawei",
    "ant",
    "ctrip",
    "weibo",
    "iflytek",
    "sensetime",
    "nio",
    "xpeng",
    "byd",
]

_DEFAULT_JOB_CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都"]


@dataclass
class JobFetchResult:
    slug: str
    job_count: int
    new_count: int
    paths: dict[str, str]
    sources: dict[str, dict]
    warnings: list[str] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "job_count": self.job_count,
            "new_count": self.new_count,
            "paths": self.paths,
            "sources": self.sources,
            "warnings": self.warnings,
            "jobs": self.jobs,
        }


def _build_queries(config: JobFetchConfig, role_label: str) -> list[str]:
    if config.keywords:
        return [q.strip() for q in config.keywords if q and q.strip()]

    scrape_queries = classify_search_queries(
        roles=[role_label],
        companies=config.companies or None,
        role_id=config.role_id or None,
    )
    if scrape_queries:
        return scrape_queries

    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        text = " ".join(q.split())
        if text and text not in seen:
            seen.add(text)
            queries.append(text)

    add(role_label)
    if config.role_id:
        preset = get_tech_role(config.role_id)
        if preset:
            add(preset.search_as)
            for kw in preset.keywords:
                add(kw)
    for company in config.companies:
        add(f"{company} {role_label}")
    return queries


def fetch_jobs(config: JobFetchConfig, jobs_root) -> JobFetchResult:
    from pathlib import Path

    root = Path(jobs_root)
    role_label = resolve_role_label(config.role_id or None, config.role or None)
    queries = _build_queries(config, role_label)
    connector_ids = resolve_connector_ids(
        sources=config.sources or None,
        companies=config.companies,
        include_aggregators=config.include_aggregators,
        include_job_pro=config.use_job_pro,
    )

    canonical = [normalize_company_name(c) for c in config.companies]
    canonical = [c for c in canonical if c]
    job_pro_keys = resolve_job_pro_keys(canonical) if canonical else list(_DEFAULT_JOB_PRO_KEYS)

    all_jobs: list[JobPosting] = []
    sources_meta: dict[str, dict] = {}
    warnings: list[str] = []
    cities = [c.strip() for c in config.cities if c and c.strip()] or list(_DEFAULT_JOB_CITIES)

    for cid in connector_ids:
        if cid == "job_pro":
            connector = build_connector(
                cid,
                job_pro_keys=job_pro_keys,
                job_pro_scope=config.job_pro_scope,
                job_pro_details=config.job_pro_details,
            )
        elif cid == "boss_zhipin":
            connector = build_connector(cid, boss_cdp_prefer=config.boss_cdp)
        else:
            connector = build_connector(cid)
        if connector is None:
            warnings.append(f"未知来源: {cid}")
            continue

        if cid == "boss_zhipin":
            boss_jobs: list[JobPosting] = []
            city_status: list[str] = []
            for city in cities[:6]:
                result = connector.search(
                    queries,
                    city=city,
                    max_per_query=config.max_per_query,
                )
                city_status.append(f"{city}:{len(result.jobs)}")
                if result.status == "degraded":
                    warnings.append(f"Boss {city}: {result.message}")
                boss_jobs.extend(result.jobs)
            sources_meta[cid] = {
                "status": "ok" if boss_jobs else "degraded",
                "message": f"{len(boss_jobs)} jobs ({', '.join(city_status)})",
                "count": len(boss_jobs),
                "cities": cities[:6],
                **connector.to_source_meta(),
            }
            all_jobs.extend(boss_jobs)
            continue

        result = connector.search(
            queries,
            city=cities[0] if cities else None,
            max_per_query=config.max_per_query,
        )
        sources_meta[cid] = {
            "status": result.status,
            "message": result.message,
            "count": len(result.jobs),
            **connector.to_source_meta(),
        }
        if result.status == "degraded":
            warnings.append(result.message)
        all_jobs.extend(result.jobs)

    # dedupe across sources (same title+company+city)
    deduped: list[JobPosting] = []
    seen_keys: set[str] = set()
    for job in all_jobs:
        key = f"{job.company}|{job.title}|{job.city or ''}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(job)

    job_pro_count = sum(1 for j in deduped if "job_pro" in (j.source or ""))
    enrich_cap = min(len(deduped), max(job_pro_count, 200)) if config.job_pro_details else 0
    enrich_jobs_descriptions(
        deduped,
        max_enrich=enrich_cap,
        skip_boss_bulk=True,
    )

    backfilled = backfill_bytedance_posted_at(deduped, queries, max_per_query=config.max_per_query)
    recency_meta: dict = {}
    if config.job_recency_days > 0:
        deduped, recency_meta = filter_official_jobs_by_recency(
            deduped,
            window_days=config.job_recency_days,
        )
    deduped = sort_jobs_by_posted_at(deduped)

    canonical_rid = canonical_role_id(config.role_id) or config.role_id
    bank_posts: list = []
    banks_root = banks_dir()
    for row in banks_matching_role(
        banks_root,
        role_label,
        config.companies,
        role_id=canonical_rid or config.role_id,
    ):
        bank_posts.extend(load_cached_raw_posts(banks_root, row["slug"]) or [])

    interview_meta = attach_interview_context(
        deduped,
        bank_posts,
        discover_missing=not config.skip_interview_discover,
        max_discover_jobs=15 if not config.skip_interview_discover else 0,
        max_per_query=6,
    )

    slug = jobs_snapshot_slug(role_label, config.companies, config.cities)
    paths = write_snapshot(
        root,
        slug,
        deduped,
        role=role_label,
        role_id=canonical_rid,
        companies=config.companies,
        cities=config.cities,
        sources=sources_meta,
        queries=queries,
    )

    new_count = sum(1 for j in deduped if j.is_new)
    if interview_meta.get("matched_jobs"):
        warnings.append(
            f"面经关联: {interview_meta['matched_jobs']} 个岗位有近3月面经"
        )
    if interview_meta.get("discovered_posts"):
        warnings.append(
            f"牛客补充搜索: {interview_meta['discovered_posts']} 条帖用于缺面经岗位"
        )
    if backfilled:
        warnings.append(f"字节官网补全发布日期: {backfilled} 条")
    if recency_meta.get("official_before"):
        warnings.append(
            f"官网近{recency_meta.get('window_days', 60)}天: "
            f"保留 {recency_meta.get('official_kept', 0)}，"
            f"无日期剔除 {recency_meta.get('official_dropped_no_date', 0)}，"
            f"超期剔除 {recency_meta.get('official_dropped_old', 0)}"
        )

    return JobFetchResult(
        slug=slug,
        job_count=len(deduped),
        new_count=new_count,
        paths=paths,
        sources={
            **sources_meta,
            "interview_link": interview_meta,
            "recency": recency_meta,
            "bytedance_dates_backfilled": backfilled,
        },
        warnings=warnings,
        jobs=[j.to_dict() for j in deduped],
    )


def list_job_snapshots(jobs_root) -> list[dict]:
    from pathlib import Path

    return list_snapshots(Path(jobs_root))


def get_job_snapshot(jobs_root, slug: str) -> dict | None:
    from pathlib import Path

    return load_snapshot(Path(jobs_root), slug)


def enrich_job_in_snapshot(jobs_root, slug: str, job_dict: dict) -> dict:
    """补全单条岗位正文并写回缓存。"""
    from pathlib import Path

    root = Path(jobs_root)
    job = JobPosting.from_dict(job_dict)
    enriched = enrich_job_description(job)
    if enriched and slug:
        patch_job_description(root, slug, job.source, job.source_id, job.description)
    return {
        "enriched": enriched,
        "description": job.description,
        "source": job.source,
        "source_id": job.source_id,
    }


def catalog_job_sources() -> list[dict]:
    return list_job_sources()
