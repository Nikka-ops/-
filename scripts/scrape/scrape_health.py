"""抓取健康状态 — 每个数据源记录最近一次运行结果，供 UI/用户/定时任务查看。

失败不再是静默的：cookie 失效、风控、零产出都会落到一个可读的状态文件里，
并给出下一步该做什么（human-readable next-step）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import cache_dir


def health_path() -> Path:
    return cache_dir() / "daily" / "scrape_health.json"


def _load() -> dict[str, Any]:
    p = health_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def record(
    source: str,
    *,
    status: str,           # ok | partial | auth_expired | risk_control | empty | error
    detail: str = "",
    count: int = 0,
    hit_rate: float | None = None,
    next_step: str = "",
) -> Path:
    """Record one source's last run. Returns the health file path."""
    data = _load()
    data[source] = {
        "status": status,
        "detail": detail,
        "count": count,
        "hit_rate": hit_rate,
        "next_step": next_step,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    p = health_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def summary() -> dict[str, Any]:
    return _load()


# Canonical next-step hints so messaging stays consistent across sources.
NEXT_STEP_XHS_AUTH = (
    "小红书登录已失效：在专用 Chrome（CDP 9223）重新登录，"
    "再运行 python -m scripts.tools.refresh_cookies xhs 更新 Cookie。"
)
NEXT_STEP_BOSS_RISK = (
    "Boss 详情接口触发风控：停止手动抓取 1–2 天，让每日任务小批量恢复；不要连续重刷。"
)
