"""大厂官方招聘站连接器注册表。"""
from __future__ import annotations

from scripts.corpus.classify import _COMPANY_ALIASES
from scripts.jobs.base import JobConnector
from scripts.jobs.connectors.boss_zhipin import BossZhipinConnector
from scripts.jobs.connectors.bytedance import ByteDanceConnector
from scripts.jobs.connectors.job_pro import (
    COMPANY_TO_JOB_PRO_KEY,
    JobProConnector,
    resolve_job_pro_keys,
)

# connector_id -> 官方招聘主体（InterviewRadar 内置，可与 job-pro 并存）
CAREER_SITE_CONNECTORS: dict[str, type[JobConnector]] = {
    "bytedance": ByteDanceConnector,
}

# 聚合 / 第三方
AGGREGATOR_CONNECTORS: dict[str, type[JobConnector]] = {
    "boss_zhipin": BossZhipinConnector,
    "job_pro": JobProConnector,
}

# 公司名（canonical）-> 优先拉取的官方站 connector id
COMPANY_CAREER_SITES: dict[str, list[str]] = {
    "字节跳动": ["job_pro"],
    "腾讯": ["job_pro"],
    "阿里巴巴": ["job_pro"],
    "美团": ["job_pro"],
    "百度": ["job_pro"],
    "华为": ["job_pro"],
    "快手": ["job_pro"],
    "网易": ["job_pro"],
    "滴滴": ["job_pro"],
    "京东": ["job_pro"],
    "拼多多": ["job_pro"],
    "小米": ["job_pro"],
    "哔哩哔哩": ["job_pro"],
    "小红书": ["job_pro"],
    "科大讯飞": ["job_pro"],
    "商汤": ["job_pro"],
}

# 展示用元数据（含尚未实现的站点，便于 UI 列出规划能力）
CAREER_SITE_CATALOG: list[dict] = [
    {
        "id": "job_pro",
        "label": "job-pro（开源 50 家）",
        "kind": "opensource",
        "status": "live",
        "repo": "https://github.com/HA7CH/job-pro",
        "requires": "Node.js 18+ 或 npm i -g job-pro",
    },
    {"id": "boss_zhipin", "label": "Boss直聘", "kind": "aggregator", "status": "cookie_required"},
    {"id": "bytedance", "label": "字节跳动招聘（内置）", "kind": "official", "status": "live", "company": "字节跳动"},
    {"id": "tencent", "label": "腾讯招聘", "kind": "official", "status": "via_job_pro", "company": "腾讯"},
    {"id": "alibaba", "label": "阿里巴巴招聘", "kind": "official", "status": "via_job_pro", "company": "阿里巴巴"},
    {"id": "meituan", "label": "美团招聘", "kind": "official", "status": "via_job_pro", "company": "美团"},
    {"id": "baidu", "label": "百度招聘", "kind": "official", "status": "via_job_pro", "company": "百度"},
    {"id": "huawei", "label": "华为招聘", "kind": "official", "status": "via_job_pro", "company": "华为"},
]


def normalize_company_name(name: str) -> str | None:
    text = (name or "").strip()
    if not text:
        return None
    lower = text.lower()
    for alias, canonical in _COMPANY_ALIASES.items():
        if alias.lower() == lower or alias == text:
            return canonical
    return text


def list_job_sources() -> list[dict]:
    out: list[dict] = []
    for item in CAREER_SITE_CATALOG:
        row = dict(item)
        row["implemented"] = row["id"] in AGGREGATOR_CONNECTORS or row["id"] in CAREER_SITE_CONNECTORS
        out.append(row)
    return out


def resolve_connector_ids(
    *,
    sources: list[str] | None = None,
    companies: list[str] | None = None,
    include_aggregators: bool = True,
    include_job_pro: bool = True,
) -> list[str]:
    """Resolve which connectors to run."""
    if sources:
        return [s for s in sources if s in AGGREGATOR_CONNECTORS or s in CAREER_SITE_CONNECTORS]

    ids: list[str] = []
    if include_aggregators:
        ids.append("boss_zhipin")

    if include_job_pro and "job_pro" not in ids:
        ids.append("job_pro")

    canonical_companies = [normalize_company_name(c) for c in (companies or [])]
    canonical_companies = [c for c in canonical_companies if c]

    if canonical_companies:
        for company in canonical_companies:
            for cid in COMPANY_CAREER_SITES.get(company, []):
                if cid not in ids and cid != "job_pro":
                    ids.append(cid)
    elif not sources:
        for cid in CAREER_SITE_CONNECTORS:
            if cid not in ids:
                ids.append(cid)

    return ids


def build_connector(connector_id: str, **kwargs) -> JobConnector | None:
    cls = AGGREGATOR_CONNECTORS.get(connector_id) or CAREER_SITE_CONNECTORS.get(connector_id)
    if cls is None:
        return None
    if connector_id == "job_pro":
        company_keys = kwargs.get("job_pro_keys") or []
        return JobProConnector(
            company_keys=company_keys,
            scope=str(kwargs.get("job_pro_scope") or "social"),
            with_details=bool(kwargs.get("job_pro_details", True)),
        )
    if connector_id == "boss_zhipin":
        return BossZhipinConnector(prefer_cdp=bool(kwargs.get("boss_cdp_prefer")))
    return cls()
