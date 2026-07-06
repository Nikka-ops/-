"""Normalize company names: subsidiaries → parent, drop non-company noise."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from scripts.config import company_aliases_path

_DEFAULT_SUBSIDIARIES: dict[str, str] = {
    "淘天": "阿里巴巴",
    "蚂蚁": "阿里巴巴",
    "蚂蚁集团": "阿里巴巴",
    "WXG": "腾讯",
    "微信小店": "腾讯",
    "TikTok": "字节跳动",
    "虾皮": "Shopee",
    "希音": "Shein",
}

_DEFAULT_NOT_COMPANIES: frozenset[str] = frozenset(
    {
        "ai",
        "agent",
        "llm",
        "rag",
        "mcp",
        "langchain",
        "双非",
        "实习",
        "校招",
        "社招",
        "秋招",
        "春招",
        "面经",
        "面试",
        "未标注",
        "其他",
        "互联网大厂",
        "社招",
        "golang",
        "26",
        "25",
        "24",
    }
)

_DEFAULT_NOT_COMPANY_PATTERNS: tuple[str, ...] = (
    r"^\d{1,2}$",
    r"^\d{2}年$",
    r"^\d{2}届",
    r"实习$",
    r"^27实习|^26实习|^25实习",
    r"菜鸡|小硕|原力健康",
    r"社招|golang",
)

_DEFAULT_PARENT_CANONICAL: dict[str, str] = {
    "字节跳动": "字节跳动",
    "腾讯": "腾讯",
    "阿里巴巴": "阿里巴巴",
}


def reload_company_aliases_cache() -> None:
    """Clear cached YAML config (for tests)."""
    _load_aliases_config.cache_clear()


@lru_cache(maxsize=1)
def _load_aliases_config() -> tuple[dict[str, str], frozenset[str], re.Pattern[str], dict[str, str]]:
    subsidiaries = dict(_DEFAULT_SUBSIDIARIES)
    not_companies = set(_DEFAULT_NOT_COMPANIES)
    patterns = list(_DEFAULT_NOT_COMPANY_PATTERNS)
    parent_canonical = dict(_DEFAULT_PARENT_CANONICAL)

    path = company_aliases_path()
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                _merge_aliases_config(raw, subsidiaries, not_companies, patterns, parent_canonical)
        except (OSError, yaml.YAMLError, TypeError, ValueError):
            pass

    pattern_re = re.compile(
        r"(?:" + "|".join(f"(?:{p})" for p in patterns) + r")",
        re.I,
    )
    return subsidiaries, frozenset(not_companies), pattern_re, parent_canonical


def _merge_aliases_config(
    raw: dict[str, Any],
    subsidiaries: dict[str, str],
    not_companies: set[str],
    patterns: list[str],
    parent_canonical: dict[str, str],
) -> None:
    subs = raw.get("subsidiaries")
    if isinstance(subs, dict):
        for key, val in subs.items():
            if key and val:
                subsidiaries[str(key).strip()] = str(val).strip()

    block = raw.get("not_companies")
    if isinstance(block, list):
        for item in block:
            if item is not None and str(item).strip():
                not_companies.add(str(item).strip().lower())

    pats = raw.get("not_company_patterns")
    if isinstance(pats, list):
        for item in pats:
            if item is not None and str(item).strip():
                patterns.append(str(item).strip())

    parents = raw.get("parent_canonical")
    if isinstance(parents, dict):
        for key, val in parents.items():
            if key and val:
                parent_canonical[str(key).strip()] = str(val).strip()


def _is_not_company(name: str) -> bool:
    _, not_companies, pattern_re, _ = _load_aliases_config()
    raw = (name or "").strip()
    if not raw or len(raw) < 2:
        return True
    if raw.lower() in not_companies:
        return True
    if pattern_re.search(raw):
        return True
    if re.fullmatch(r"[\d\.\-\s]+", raw):
        return True
    return False


def normalize_company_name(name: str | None) -> str | None:
    """Return canonical company label, or None if not a real company."""
    if not name or not str(name).strip():
        return None
    subsidiaries, _, _, parent_canonical = _load_aliases_config()
    raw = str(name).strip()
    if _is_not_company(raw):
        return None

    key = raw.lower()
    for alias, parent in subsidiaries.items():
        if alias.lower() == key or alias.lower() == raw.lower():
            return parent

    for alias, parent in sorted(subsidiaries.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 2 and alias.lower() in key:
            return parent

    if raw in parent_canonical:
        return parent_canonical[raw]

    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·]{2,20}", raw):
        if _is_not_company(raw):
            return None
        return raw

    return None


def infer_company_from_text_normalized(text: str) -> str | None:
    """Scan text for known company aliases; return normalized parent."""
    if not text or not text.strip():
        return None
    subsidiaries, _, _, _ = _load_aliases_config()
    lower = text.lower()
    for alias, parent in sorted(subsidiaries.items(), key=lambda x: -len(x[0])):
        if len(alias) < 2:
            continue
        if alias.lower() in lower or alias in text:
            return parent
    return None
