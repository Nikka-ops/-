"""Import Xiaohongshu notes from Spider_XHS JSON exports (no live crawl)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import cache_dir, spider_xhs_home
from scripts.connectors.xiaohongshu import XiaohongshuConnector, posts_from_notes
from scripts.scrape.normalize_xhs import normalize


def _export_search_dirs() -> list[Path]:
    dirs = [
        spider_xhs_home() / "data" / "xhs" / "json",
        cache_dir() / "xhs",
    ]
    return [d for d in dirs if d.is_dir()]


def collect_xhs_export_files(
    *,
    max_age_days: int = 30,
    max_files: int = 30,
) -> list[Path]:
    """Gather recent ``search_contents_*.json`` from Spider_XHS and local cache."""
    cutoff = time.time() - max_age_days * 86400
    found: list[tuple[float, Path]] = []
    patterns = ("search_contents_*.json", "xhs_export*.json", "search_*.json")
    for root in _export_search_dirs():
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime < cutoff:
                    continue
                found.append((mtime, path))
    found.sort(key=lambda x: x[0], reverse=True)
    seen_paths: set[str] = set()
    unique: list[Path] = []
    for _, p in found:
        key = str(p.resolve())
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique.append(p)
    return unique[:max_files]


def _merge_notes_from_files(paths: list[Path]) -> list[dict]:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        notes = raw if isinstance(raw, list) else raw.get("notes") or raw.get("data") or []
        if not isinstance(notes, list):
            continue
        normalized = normalize(notes)
        for note in normalized:
            nid = str(note.get("note_id") or "").strip()
            if nid and nid in seen_ids:
                continue
            if nid:
                seen_ids.add(nid)
            merged.append(note)
    return merged


def xhs_scrape_status() -> dict:
    """Diagnostics for Web UI / doctor."""
    from scripts.config import xhs_cookies_configured, xhs_cookies_source

    paths = collect_xhs_export_files(max_age_days=30)
    latest_mtime = max((p.stat().st_mtime for p in paths), default=0)
    latest_iso = (
        datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if latest_mtime
        else None
    )
    home = spider_xhs_home()
    node_ok = (home / "node_modules").is_dir()
    return {
        "driver": "spider_xhs",
        "cookie_configured": xhs_cookies_configured(),
        "cookie_source": xhs_cookies_source(),
        "spider_xhs_home": str(home),
        "spider_xhs_installed": (home / "apis" / "xhs_pc_apis.py").is_file(),
        "node_modules_ready": node_ok,
        "export_files": len(paths),
        "latest_export": str(paths[0]) if paths else None,
        "latest_export_at": latest_iso,
        "search_dirs": [str(d) for d in _export_search_dirs()],
    }


def run_safe_xhs_scrape(
    keywords: list[str],
    *,
    batch_size: int = 2,
    pause_seconds: float | None = None,
    limit_keywords: bool = True,
) -> dict:
    """Low-frequency Spider_XHS keyword search (CDP Chrome or XHS_COOKIES)."""
    from scripts.config import xhs_batch_pause_seconds, xhs_cookies_configured
    from scripts.scrape.spider_xhs_driver import SpiderXHSDriver, SpiderXHSScrapeError

    if not xhs_cookies_configured():
        raise ValueError(
            "小红书 Cookie 未配置。请启动专用 Chrome 并登录（bash scripts/tools/start-xhs-cdp-chrome.sh），"
            "或设置 XHS_COOKIES / XHS_WEB_SESSION。"
        )
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    if not cleaned:
        raise ValueError("keywords required")
    if limit_keywords:
        from scripts.config import xhs_max_keywords_per_run

        cleaned = cleaned[:xhs_max_keywords_per_run()]
    pause = pause_seconds if pause_seconds is not None else xhs_batch_pause_seconds()
    driver = SpiderXHSDriver()
    out = driver.scrape_xhs(
        cleaned,
        pause_seconds=max(1.0, pause / max(1, batch_size)),
    )
    return {
        "ok": True,
        "keywords": cleaned,
        "export_path": str(out),
        "pause_seconds": pause,
        "batch_size": batch_size,
        "driver": "spider_xhs",
    }


def run_full_xhs_scrape(
    keywords: list[str],
    *,
    batch_size: int = 2,
    pause_seconds: float | None = None,
    keywords_per_run: int = 8,
) -> dict:
    """Run all keywords in multiple Spider_XHS batches (full scrape)."""
    from scripts.config import xhs_batch_pause_seconds, xhs_cookies_configured
    from scripts.scrape.spider_xhs_driver import SpiderXHSDriver

    if not xhs_cookies_configured():
        raise ValueError("小红书 Cookie 未配置")
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    if not cleaned:
        raise ValueError("keywords required")
    pause = pause_seconds if pause_seconds is not None else xhs_batch_pause_seconds()
    chunk = max(1, keywords_per_run)
    driver = SpiderXHSDriver()
    exports: list[str] = []
    batches_run = 0
    for i in range(0, len(cleaned), chunk):
        batch = cleaned[i : i + chunk]
        if i and pause > 0:
            time.sleep(pause)
        out = driver.scrape_xhs(
            batch,
            pause_seconds=max(1.0, pause / max(1, batch_size)),
        )
        exports.append(str(out))
        batches_run += 1
    return {
        "ok": True,
        "keywords_total": len(cleaned),
        "batches_run": batches_run,
        "export_paths": exports,
        "last_export_path": exports[-1] if exports else None,
        "driver": "spider_xhs",
    }


def load_xhs_posts_from_exports(
    *,
    enable_ocr: bool = True,
    max_age_days: int | None = None,
    max_files: int | None = None,
) -> tuple[list, dict]:
    """Load RawPosts from on-disk Spider_XHS exports (cached OCR in corpus_cache)."""
    from scripts.config import xhs_export_max_age_days, xhs_export_max_files

    age_days = max_age_days if max_age_days is not None else xhs_export_max_age_days()
    file_limit = max_files if max_files is not None else xhs_export_max_files()
    paths = collect_xhs_export_files(max_age_days=age_days, max_files=file_limit)
    meta: dict = {
        "status": "missing",
        "files": len(paths),
        "paths": [str(p) for p in paths[:5]],
        "note_count": 0,
        "post_count": 0,
        "max_age_days": age_days,
        "driver": "spider_xhs",
    }
    if not paths:
        return [], meta

    notes = _merge_notes_from_files(paths)
    meta["note_count"] = len(notes)
    if not notes:
        meta["status"] = "empty"
        return [], meta

    staging = cache_dir() / "xhs"
    staging.mkdir(parents=True, exist_ok=True)
    merged_path = staging / "_merged_export.json"
    merged_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    conn = XiaohongshuConnector(
        export_path=str(merged_path),
        enable_image_ocr=enable_ocr,
        asset_root=staging / "assets",
        ocr_root=staging / "ocr",
    )
    # 导出加载不做时效裁剪（ ingest 阶段统一 filter_recent ）
    result = conn.search([])
    notes_for_count = _merge_notes_from_files(paths)
    posts_no_window = posts_from_notes(notes_for_count, window_days=0)
    meta["note_count_raw"] = len(notes_for_count)
    meta["post_count_before_recency"] = len(posts_no_window)
    meta["status"] = result.status
    meta["message"] = result.message
    meta["post_count"] = len(result.posts)
    meta["ocr_mode"] = "deep" if enable_ocr else "fast"
    meta["imported_at"] = datetime.now(timezone.utc).isoformat()
    return result.posts, meta
