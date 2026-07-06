"""Preset company groups for Web UI filters (互联网大厂 + 其他)."""
from __future__ import annotations

# 互联网 / 中大厂（默认抓取 / UI 主栏）
INTERNET_GIANTS: tuple[str, ...] = (
    "字节跳动",
    "腾讯",
    "阿里巴巴",
    "美团",
    "百度",
    "京东",
    "拼多多",
    "快手",
    "网易",
    "滴滴",
    "小米",
    "哔哩哔哩",
    "小红书",
    "华为",
    "携程",
    "微博",
    "商汤",
    "MiniMax",
    "微软",
    "谷歌",
    "OPPO",
    "vivo",
    "Shein",
    "Shopee",
)

# 制造业等：不在 UI 单独分栏；面经出现则计入「其他」
MANUFACTURING_GIANTS: tuple[str, ...] = (
    "比亚迪",
    "蔚来",
    "理想",
    "小鹏",
    "宁德时代",
    "上汽",
    "吉利",
    "格力",
    "海尔",
    "三一重工",
    "顺丰",
)

COMPANY_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("internet", "互联网大厂", INTERNET_GIANTS),
)

_ALL_PRESET: frozenset[str] = frozenset(INTERNET_GIANTS)

OTHER_COMPANY_LABEL = "其他"


def all_preset_companies() -> list[str]:
    return sorted(_ALL_PRESET)


def is_preset_company(name: str) -> bool:
    return (name or "").strip() in _ALL_PRESET


def resolve_company_list(raw: str | list[str] | None) -> list[str]:
    """Parse CLI/UI company args; ``all`` / ``全国大厂`` → internet preset list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.lower() in {"all", "全国大厂", "大厂", "preset"}:
            return all_preset_companies()
        return [c.strip() for c in text.replace("，", ",").split(",") if c.strip()]
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if s.lower() in {"all", "全国大厂", "大厂", "preset"}:
            return all_preset_companies()
        if s:
            out.append(s)
    return out


def list_company_groups() -> list[dict]:
    return [
        {"id": gid, "label": label, "companies": list(companies)}
        for gid, label, companies in COMPANY_GROUPS
    ]
