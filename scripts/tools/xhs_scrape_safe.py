#!/usr/bin/env python3
"""Safe Xiaohongshu scrape via Spider_XHS (CDP Chrome cookie, low frequency).

推荐工作流（面经以小红书为主、降低封号风险）:

1. 用**专用小号**在浏览器登录小红书（不要用主号）
2. 复制 web_session 到项目 .env: XHS_WEB_SESSION=...
3. 每天 1～2 次、每次 2～4 个关键词:

   uv run python -m scripts.tools.xhs_scrape_safe --role-id ai_app

4. Web UI 勾选「使用小红书本地导出」后点「抓取并生成面经库」

勿在 Web UI 勾选「网页内联网重新抓小红书」——易触发风控。
"""
from __future__ import annotations

import argparse
import sys

from scripts.corpus.company_catalog import resolve_company_list
from scripts.config import bootstrap_env, xhs_web_session_configured
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.xhs_export import run_safe_xhs_scrape
from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError


def _keywords_from_role(role_id: str, companies: list[str]) -> list[str]:
    return xhs_keywords_for_role(role_id, companies)


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="Safe XHS scrape (batched keywords, cookie login)")
    parser.add_argument(
        "--keywords",
        default="",
        help="逗号分隔搜索词，建议每次不超过 4 个",
    )
    parser.add_argument("--role-id", default="", help="按岗位自动生成关键词（如 ai_app）")
    parser.add_argument(
        "--companies",
        default="",
        help="可选公司，逗号分隔或 all=全国大厂；与 --role-id 合用",
    )
    parser.add_argument("--batch-size", type=int, default=2, help="每批关键词数量")
    parser.add_argument("--pause", type=float, default=60.0, help="批间暂停秒数（默认 60）")
    args = parser.parse_args(argv)

    keywords: list[str] = []
    if args.keywords.strip():
        keywords = [k.strip() for k in args.keywords.replace("，", ",").split(",") if k.strip()]
    elif args.role_id.strip():
        companies = resolve_company_list(args.companies)
        keywords = _keywords_from_role(args.role_id.strip(), companies)
    if not keywords:
        print("请提供 --keywords 或 --role-id", file=sys.stderr)
        return 1

    if not xhs_web_session_configured():
        print(
            "未设置 XHS_WEB_SESSION。专用小号登录小红书 → DevTools → Cookies → web_session\n"
            "写入 .env: XHS_WEB_SESSION=...",
            file=sys.stderr,
        )
        return 1

    print(f"开始抓取 {len(keywords)} 个关键词（每批 {args.batch_size} 个，批间 {args.pause}s）…")
    try:
        result = run_safe_xhs_scrape(
            keywords,
            batch_size=max(1, args.batch_size),
            pause_seconds=max(15.0, args.pause),
        )
    except (SpiderXHSScrapeError, FileNotFoundError, ValueError) as exc:
        print(f"抓取失败: {exc}", file=sys.stderr)
        return 1

    print(f"完成 → {result['export_path']}")
    print("在 Web UI 勾选「使用小红书本地导出」后点「抓取并生成面经库」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
