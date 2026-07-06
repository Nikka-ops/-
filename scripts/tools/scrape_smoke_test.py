#!/usr/bin/env python3
"""Smoke test for 牛客 + 小红书抓取链路(分类 / 矩阵 / connector 健康检查).

用法:
  .venv/bin/python -m scripts.tools.scrape_smoke_test
  .venv/bin/python -m scripts.tools.scrape_smoke_test --nowcoder-urls URL1 URL2
  .venv/bin/python -m scripts.tools.scrape_smoke_test --xhs-live --keywords "字节 AI 应用开发 面经"
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import requests

from scripts.connectors.nowcoder import NowCoderConnector
from scripts.connectors.xiaohongshu import XiaohongshuConnector
from scripts.corpus.classify import classify_search_queries
from scripts.corpus.group import taxonomy_summary
from scripts.corpus.recency import filter_recent
from scripts.scrape.xhs_export import run_safe_xhs_scrape
from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _probe_nowcoder_direct(url: str) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        blocked = "aliyun_waf" in resp.text
        ok = "nc-slate-editor-content" in resp.text and not blocked
        return {"url": url, "status": resp.status_code, "ok": ok, "waf": blocked, "len": len(resp.text)}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="InterviewRadar scrape smoke test")
    parser.add_argument("--roles", nargs="+", default=["AI 应用开发"])
    parser.add_argument("--companies", nargs="+", default=["字节跳动", "美团"])
    parser.add_argument("--nowcoder-urls", nargs="*", default=[])
    parser.add_argument("--xhs-live", action="store_true", help="Run Spider_XHS driver (needs login)")
    parser.add_argument("--keywords", nargs="+", default=["字节 AI 应用开发 面经"])
    parser.add_argument("--out", default="corpus_cache/scrape_smoke_report.json")
    args = parser.parse_args()

    report: dict = {"queries": classify_search_queries(roles=args.roles, companies=args.companies)}

    posts = []
    if args.nowcoder_urls:
        probes = [_probe_nowcoder_direct(u) for u in args.nowcoder_urls]
        report["nowcoder_probes"] = probes
        result = NowCoderConnector(post_urls=args.nowcoder_urls).search(report["queries"])
        report["nowcoder"] = {"status": result.status, "message": result.message, "count": len(result.posts)}
        posts.extend(result.posts)

    if args.xhs_live:
        try:
            scrape_meta = run_safe_xhs_scrape(args.keywords, limit_keywords=False)
            path = Path(scrape_meta["export_path"])
            result = XiaohongshuConnector(export_path=str(path), enable_image_ocr=False).search([])
            report["xiaohongshu"] = {
                "status": result.status,
                "message": result.message,
                "export": str(path),
                "driver": "spider_xhs",
            }
            posts.extend(result.posts)
        except (SpiderXHSScrapeError, FileNotFoundError, ValueError) as exc:
            report["xiaohongshu"] = {"status": "degraded", "message": str(exc)}

    posts = filter_recent(posts, today=date.today())
    report["taxonomy"] = taxonomy_summary(posts)
    report["posts"] = [p.to_dict() for p in posts]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "posts"}, ensure_ascii=False, indent=2))
    print(f"\nWrote {out} ({len(posts)} posts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
