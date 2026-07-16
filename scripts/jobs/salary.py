"""薪资分析 — 解析 Boss/官网 salary 字段，输出分布与公司对比。

支持格式："20-35K"、"20-35K·14薪"、"300-500元/天"（实习日薪）、"面议"。
月薪统一为 K；日薪单独归入 intern 桶。
"""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

_MONTHLY = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*K", re.I)
_DAILY = re.compile(r"(\d+)\s*-\s*(\d+)\s*元/天")
_BONUS = re.compile(r"·\s*(\d+)\s*薪")

_BUCKETS = ((0, 15), (15, 25), (25, 35), (35, 50), (50, 80), (80, 999))


def parse_salary(text: str) -> dict | None:
    """→ {kind: monthly|daily, lo, hi, months} 或 None（面议/无法解析）。"""
    t = (text or "").strip()
    if not t:
        return None
    m = _MONTHLY.search(t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        months = 12
        b = _BONUS.search(t)
        if b:
            months = int(b.group(1))
        return {"kind": "monthly", "lo": lo, "hi": hi, "months": months}
    d = _DAILY.search(t)
    if d:
        return {"kind": "daily", "lo": float(d.group(1)), "hi": float(d.group(2)), "months": 0}
    return None


def _mid(s: dict) -> float:
    return (s["lo"] + s["hi"]) / 2


def analyse_salaries(jobs: list[dict], *, min_company_count: int = 3) -> dict:
    monthly_mids: list[float] = []
    daily_mids: list[float] = []
    by_company: dict[str, list[float]] = defaultdict(list)

    for job in jobs:
        s = parse_salary(str(job.get("salary") or ""))
        if not s:
            continue
        if s["kind"] == "daily":
            daily_mids.append(_mid(s))
            continue
        mid = _mid(s)
        monthly_mids.append(mid)
        company = (job.get("company") or "").strip()
        if company:
            by_company[company].append(mid)

    buckets = []
    for lo, hi in _BUCKETS:
        n = sum(1 for m in monthly_mids if lo <= m < hi)
        if n:
            label = f"{lo}-{hi}K" if hi < 999 else f"{lo}K+"
            buckets.append({"range": label, "count": n})

    companies = [
        {
            "company": c,
            "count": len(mids),
            "median_k": round(median(mids), 1),
            "min_k": round(min(mids), 1),
            "max_k": round(max(mids), 1),
        }
        for c, mids in by_company.items()
        if len(mids) >= min_company_count
    ]
    companies.sort(key=lambda r: -r["median_k"])

    return {
        "sample": len(monthly_mids),
        "median_k": round(median(monthly_mids), 1) if monthly_mids else 0,
        "buckets": buckets,
        "companies": companies[:15],
        "intern_daily": {
            "sample": len(daily_mids),
            "median": round(median(daily_mids)) if daily_mids else 0,
        },
    }
