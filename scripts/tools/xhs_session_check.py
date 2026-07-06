#!/usr/bin/env python3
"""检查小红书搜索会话是否可用（抓取前自检）。"""
from __future__ import annotations

import sys

from scripts.config import bootstrap_env, xhs_web_session_configured
from scripts.scrape.spider_xhs_driver import (
    SpiderXHSScrapeError,
    _HTTP_461_HINT,
    _probe_search,
    _spider_xhs_runtime,
    resolve_xhs_cookies,
)


def main() -> int:
    bootstrap_env()
    if not xhs_web_session_configured():
        print("未配置 Cookie。运行: bash scripts/tools/start-xhs-cdp-chrome.sh")
        return 1
    cookies = resolve_xhs_cookies()
    try:
        with _spider_xhs_runtime(__import__("pathlib").Path.home() / ".spider_xhs"):
            status, count = _probe_search(cookies)
    except SpiderXHSScrapeError as exc:
        print(exc)
        return 1
    print(f"HTTP {status} · 探测「面经」≈ {count} 条")
    if status == 461:
        print(_HTTP_461_HINT)
        return 1
    if count == 0:
        print("会话可用但探测无结果 — 可试抓，若仍 0 条请浏览器手动搜一次")
        return 0
    print("可以抓取: python -m scripts.tools.xhs_incremental --role-id data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
