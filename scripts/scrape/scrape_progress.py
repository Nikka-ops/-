"""抓取/构建进度 — 写入一个 JSON 文件,供 UI 轮询显示进度条 + 人话状态。

同步阻塞的抓取端点无法边跑边推送,于是把进度落盘,前端 poll /api/scrape/progress。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.config import cache_dir


def progress_path() -> Path:
    return cache_dir() / "daily" / "scrape_progress.json"


def set_progress(
    phase: str,            # scraping | filtering | ranking | answering | building | done | error
    message: str,
    *,
    current: int = 0,
    total: int = 0,
    active: bool = True,
) -> None:
    pct = round(current / total * 100) if total else (100 if phase == "done" else 0)
    payload = {
        "phase": phase,
        "message": message,
        "current": current,
        "total": total,
        "pct": pct,
        "active": active,
        "at": time.time(),
    }
    p = progress_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def clear_progress() -> None:
    set_progress("done", "完成", active=False)


def read_progress() -> dict[str, Any]:
    p = progress_path()
    if not p.is_file():
        return {"phase": "idle", "message": "", "pct": 0, "active": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"phase": "idle", "message": "", "pct": 0, "active": False}
    # 超过 5 分钟无更新视为陈旧,不再显示进行中
    if data.get("active") and (time.time() - float(data.get("at") or 0)) > 300:
        data["active"] = False
    return data
