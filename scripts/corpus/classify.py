"""Extract company and role labels from Chinese interview post metadata.

Heuristic-only: no network; search query expansion uses preset role keywords.
"""
from __future__ import annotations

import re

from scripts.corpus.company_normalize import infer_company_from_text_normalized, normalize_company_name
from scripts.corpus.tech_roles import get_tech_role

_ROUND_SUFFIX = re.compile(
    r"(?:"
    r"(?:一|二|三|四|五)面|"
    r"HR面|hr面|"
    r"面经|面试经|面试经验|面试分享|"
    r"秋招|春招|校招|社招|"
    r"经验|分享|记录|总结|攻略|整理"
    r")+$",
    re.IGNORECASE,
)

_TRAILING_NOISE = re.compile(r"[_\-—|｜].*$")

_BRACKET_PREFIX = re.compile(r"^【[^】]*】\s*")

# title like "字节 AI 应用岗" / "美团 Agent 方向面经" (no 一面/二面)
_COMPANY_ROLE_LOOSE = re.compile(
    r"^(.{2,12}?)\s+(.+?)"
    r"(?:"
    r"方向面经|方向|"
    r"应用岗|开发岗|产品岗|算法岗|"
    r"面经|面试"
    r")?\s*$",
    re.IGNORECASE,
)

_COMPANY_ALIASES: dict[str, str] = {
    "字节": "字节跳动",
    "字节跳动": "字节跳动",
    "bytedance": "字节跳动",
    "腾讯": "腾讯",
    "tencent": "腾讯",
    "阿里": "阿里巴巴",
    "阿里巴巴": "阿里巴巴",
    "alibaba": "阿里巴巴",
    "蚂蚁": "蚂蚁集团",
    "蚂蚁集团": "蚂蚁集团",
    "美团": "美团",
    "meituan": "美团",
    "快手": "快手",
    "kuaishou": "快手",
    "百度": "百度",
    "baidu": "百度",
    "华为": "华为",
    "huawei": "华为",
    "小米": "小米",
    "xiaomi": "小米",
    "网易": "网易",
    "netease": "网易",
    "滴滴": "滴滴",
    "didi": "滴滴",
    "拼多多": "拼多多",
    "pdd": "拼多多",
    "京东": "京东",
    "jd": "京东",
    "微软": "微软",
    "microsoft": "微软",
    "谷歌": "谷歌",
    "google": "谷歌",
    "亚马逊": "亚马逊",
    "amazon": "亚马逊",
    "商汤": "商汤",
    "sensetime": "商汤",
    "科大讯飞": "科大讯飞",
    "iflytek": "科大讯飞",
}

_ROLE_MARKERS = re.compile(
    r"(?:"
    r"开发|工程师|产品|算法|运营|设计|分析|测试|架构|研发|实习|"
    r"经理|专员|岗|科学家|研究员|顾问|管培|校招|社招|"
    r"agent|llm|rag"
    r")",
    re.IGNORECASE,
)

# title like "字节 AI 应用开发 一面面经" or "腾讯 产品经理 实习 面经"
_COMPANY_ROLE_TITLE = re.compile(
    r"^(.{2,12}?)\s+(.+?)"
    r"(?:"
    r"(?:一|二|三|四|五)面|"
    r"HR面|hr面|"
    r"面经|面试|秋招|春招|校招|社招|实习"
    r")",
    re.IGNORECASE,
)

_DESC_ROLE_MARKERS = re.compile(
    r"(?:开发|工程师|产品|算法|运营|设计|分析|测试|架构|研发|实习|经理|专员|岗)",
    re.IGNORECASE,
)

_YEAR_ONLY = re.compile(r"^20\d{2}$")


def _normalize_title(title: str) -> str:
    return _BRACKET_PREFIX.sub("", title.strip()).strip()


def _canonical_company(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or _YEAR_ONLY.match(cleaned):
        return ""
    normalized = normalize_company_name(cleaned)
    if normalized:
        return normalized
    key = cleaned.lower()
    for alias, canonical in sorted(_COMPANY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias.lower() == key or alias.lower() in key:
            parent = normalize_company_name(canonical) or canonical
            return parent
    return ""


def _clean_role(text: str) -> str:
    role = _ROUND_SUFFIX.sub("", text.strip())
    role = _TRAILING_NOISE.sub("", role)
    return role.strip()


def _looks_like_role(text: str) -> bool:
    return bool(_ROLE_MARKERS.search(text))


def _from_title(title: str) -> tuple[str | None, str | None]:
    title = _normalize_title(title)
    if not title or len(title) < 4:
        return None, None

    m = _COMPANY_ROLE_TITLE.match(title)
    if m:
        company = _canonical_company(m.group(1))
        role = _clean_role(m.group(2))
        if role and _looks_like_role(role):
            return company or None, role

    m = _COMPANY_ROLE_LOOSE.match(title)
    if m:
        company = _canonical_company(m.group(1))
        role = _clean_role(m.group(2))
        if role and _looks_like_role(role):
            return company or None, role

    # fallback: company at start + remainder looks like a role
    for alias, canonical in sorted(_COMPANY_ALIASES.items(), key=lambda x: -len(x[0])):
        idx = title.find(alias)
        if idx == -1:
            continue
        # company must be at title start or right after bracket strip
        if idx != 0:
            continue
        remainder = title[len(alias) :].strip()
        remainder = _ROUND_SUFFIX.sub("", remainder).strip()
        if remainder and _looks_like_role(remainder):
            return canonical, _clean_role(remainder)
        if remainder in ("面经", "面试", "实习"):
            return canonical, None
    return None, None


def infer_company_from_text(text: str) -> str | None:
    """Find company name anywhere in post text (title/body/tags)."""
    hit = infer_company_from_text_normalized(text)
    if hit:
        return hit
    if not text or not text.strip():
        return None
    lower = text.lower()
    for alias, canonical in sorted(_COMPANY_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) < 2:
            continue
        if alias.lower() in lower or alias in text:
            parent = normalize_company_name(canonical) or canonical
            return parent
    return None


def _from_tags(tags: list[str]) -> tuple[str | None, str | None]:
    company: str | None = None
    role: str | None = None
    for raw in tags:
        tag = raw.strip().lstrip("#")
        if not tag:
            continue
        canonical = _canonical_company(tag)
        if canonical:
            company = company or canonical
            continue
        if _looks_like_role(tag):
            role = role or _clean_role(tag)
    return company, role


def extract_company_role(
    *,
    title: str = "",
    tags: list[str] | None = None,
    desc: str = "",
) -> tuple[str | None, str | None]:
    """Return (company, role) parsed from post metadata. Either may be None."""
    company, role = _from_title(title)
    tag_company, tag_role = _from_tags(tags or [])
    company = company or tag_company
    role = role or tag_role

    if not role and desc:
        first_line = desc.strip().splitlines()[0][:80] if desc.strip() else ""
        if first_line and _DESC_ROLE_MARKERS.search(first_line):
            role = _clean_role(first_line)

    if not company:
        company = infer_company_from_text(title) or infer_company_from_text(desc)
        if not company and tags:
            company = infer_company_from_text(" ".join(tags))

    if company:
        company = _canonical_company(company)
    if role:
        role = _clean_role(role)
        if not role:
            role = None

    from scripts.corpus.role_match import refine_extracted_role

    refined = refine_extracted_role(title=title, tags=tags, desc=desc, parsed_role=role)
    if refined:
        role = refined

    return company or None, role or None


def classify_search_queries(
    *,
    roles: list[str],
    companies: list[str] | None = None,
    include_role_only: bool = True,
    role_id: str | None = None,
) -> list[str]:
    """Build 牛客 / 小红书 search keyword batches grouped by 岗位 × 公司."""
    roles = [r.strip() for r in roles if r and r.strip()]
    companies = [c.strip() for c in (companies or []) if c and c.strip()]
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = " ".join(q.split())
        if q and q not in seen:
            seen.add(q)
            queries.append(q)

    preset = get_tech_role(role_id or "") if role_id else None

    for role in roles:
        if include_role_only:
            add(f"{role} 面经")
            add(f"{role} 面试")
            add(f"{role} 实习 面经")
            add(f"{role} 校招 面经")
        if preset:
            for kw in preset.keywords:
                add(f"{kw} 面经")
                add(f"{preset.search_as} {kw}")
                add(kw)
        for company in companies:
            add(f"{company} {role} 面经")
            add(f"{company} {role} 实习 面经")
            add(f"{company} {role} 社招 面经")
            add(f"{company} {role} 一面")
            add(f"{company} {role} 二面")
    return queries
