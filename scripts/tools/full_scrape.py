#!/usr/bin/env python3
"""Full-volume scrape: all companies × all search queries (hours-long OK).

与 daily_scrape 的区别：
- 一次跑完全部牛客搜索词（非每日 24 词）
- 小红书全部关键词分批抓取（非每日 8 词）
- 更高单词条数上限、更长时效窗口

示例（小红书为主源，需配置 XHS_WEB_SESSION）:

  uv run python -m scripts.tools.full_scrape --role-id data --companies all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from scripts.corpus.company_catalog import resolve_company_list
from scripts.corpus.recency import filter_recent
from scripts.corpus.role_match import annotate_post, filter_posts_for_bank
from scripts.corpus.tech_roles import resolve_role_label
from scripts.config import (
    bootstrap_env,
    full_scrape_recency_days,
    xhs_batch_pause_seconds,
    xhs_max_keywords_per_run,
    xhs_web_session_configured,
)
from scripts.discover.nowcoder_moments import search_nowcoder_moments
from scripts.models import RawPost
from scripts.scrape.keywords import nowcoder_queries_for_role, xhs_keywords_for_role
from scripts.scrape.scrape_state import (
    append_rolling_nowcoder_posts,
    clear_full_scrape_nc_progress,
    full_scrape_nc_done_queries,
    mark_full_scrape_queries_done,
    rolling_nowcoder_path,
)
from scripts.scrape.xhs_export import run_full_xhs_scrape
from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError
from scripts.service import RunConfig, run_pipeline


def _stage_counts(posts: list[RawPost], role: str, recency_days: int) -> dict:
    annotated = [annotate_post(p) for p in posts]
    kept, dropped = filter_posts_for_bank(annotated, role)
    recent = filter_recent(kept, window_days=recency_days, today=date.today())
    return {
        "raw": len(posts),
        "after_role_filter": len(kept),
        "role_dropped": len(dropped),
        "after_recency": len(recent),
        "recency_days": recency_days,
    }


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="InterviewRadar 全量面经抓取")
    parser.add_argument("--role-id", default="data")
    parser.add_argument("--role", default="")
    parser.add_argument(
        "--companies",
        default="all",
        help="逗号分隔或 all=全国大厂",
    )
    parser.add_argument("--nowcoder-max-per-query", type=int, default=200)
    parser.add_argument("--nowcoder-max-pages", type=int, default=30)
    parser.add_argument("--nowcoder-delay", type=float, default=0.35)
    parser.add_argument("--recency-days", type=int, default=0, help="0=用 FULL_SCRAPE_RECENCY_DAYS 环境变量")
    parser.add_argument("--skip-xhs", action="store_true")
    parser.add_argument("--skip-nowcoder", action="store_true")
    parser.add_argument(
        "--skip-role-filter",
        action="store_true",
        help="跳过岗位过滤（仅调试；focus 岗位默认严格过滤）",
    )
    parser.add_argument("--resume", action="store_true", help="跳过本轮已完成的牛客搜索词")
    parser.add_argument("--xhs-batch-size", type=int, default=2, help="每批关键词数（反检测建议 2）")
    parser.add_argument("--xhs-keywords-per-run", type=int, default=0, help="0=用 XHS_MAX_KEYWORDS_PER_RUN（建议 6）")
    parser.add_argument("--xhs-pause", type=float, default=0, help="批间暂停秒数（0=默认 30）")
    parser.add_argument("--no-rebuild", action="store_true")
    parser.add_argument(
        "--fast-rebuild",
        action="store_true",
        help="重建时跳过深度 OCR（更快）",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    skip_role_filter = args.skip_role_filter

    companies = resolve_company_list(args.companies)
    role_id = args.role_id.strip()
    role_label = resolve_role_label(role_id=role_id, role_text=args.role.strip() or None)
    recency_days = args.recency_days or full_scrape_recency_days()

    report: dict = {
        "date": date.today().isoformat(),
        "role_id": role_id,
        "role": role_label,
        "company_count": len(companies),
        "recency_days": recency_days,
        "nowcoder": {},
        "xhs": {},
        "bank": {},
        "stages": {},
    }

    nc_queries = nowcoder_queries_for_role(role_id, companies)
    xhs_keys = xhs_keywords_for_role(role_id, companies)
    report["nowcoder_query_total"] = len(nc_queries)
    report["xhs_keyword_total"] = len(xhs_keys)
    xhs_keywords_per_run = args.xhs_keywords_per_run or xhs_max_keywords_per_run()
    xhs_pause = args.xhs_pause or xhs_batch_pause_seconds()

    if not args.skip_xhs:
        if not xhs_web_session_configured():
            report["xhs"]["error"] = "XHS_WEB_SESSION not configured"
            print("  小红书失败: 未配置 XHS_WEB_SESSION（面经主源，请先配置 .env）")
        else:
            print(f"小红书全量（主源）: {len(xhs_keys)} 个词，每轮 {xhs_keywords_per_run} 词，批间 {xhs_pause}s …")
            try:
                xhs_out = run_full_xhs_scrape(
                    xhs_keys,
                    batch_size=max(1, args.xhs_batch_size),
                    pause_seconds=max(15.0, xhs_pause),
                    keywords_per_run=max(1, xhs_keywords_per_run),
                )
                report["xhs"] = xhs_out
                print(f"  小红书完成 {xhs_out.get('batches_run')} 批")
            except (SpiderXHSScrapeError, FileNotFoundError, ValueError) as exc:
                report["xhs"]["error"] = str(exc)
                print(f"  小红书失败: {exc}")

    if not args.skip_nowcoder:
        nc_queries_all = list(nc_queries)
        if args.resume:
            done = full_scrape_nc_done_queries()
            nc_queries = [q for q in nc_queries_all if q not in done]
            print(
                f"牛客续跑: 已完成 {len(done)}/{len(nc_queries_all)} 词，"
                f"剩余 {len(nc_queries)} 词 …",
                flush=True,
            )
        else:
            clear_full_scrape_nc_progress()
            print(
                f"牛客全量: {len(nc_queries)} 个搜索词 × 最多 {args.nowcoder_max_per_query} 条/词 …",
                flush=True,
            )
        all_nc: list[RawPost] = []
        per_query_meta: list[dict] = []
        total_q = len(nc_queries_all)
        done_count = len(full_scrape_nc_done_queries())
        for i, q in enumerate(nc_queries):
            if i and args.nowcoder_delay > 0:
                time.sleep(args.nowcoder_delay)
            batch, row_meta = search_nowcoder_moments(
                [q],
                max_per_query=max(10, args.nowcoder_max_per_query),
                max_pages=max(5, args.nowcoder_max_pages),
                request_delay=0.15,
            )
            all_nc.extend(batch)
            added = append_rolling_nowcoder_posts(batch)
            mark_full_scrape_queries_done([q])
            row = (row_meta.get("per_query") or [{}])[0]
            per_query_meta.append(row)
            done_count = len(full_scrape_nc_done_queries())
            print(
                f"  [{done_count}/{total_q}] {q[:48]} → {len(batch)} 篇 "
                f"(本批累计 {len(all_nc)}, 滚动库+{added})",
                flush=True,
            )
        if len(nc_queries_all) and done_count >= len(nc_queries_all):
            clear_full_scrape_nc_progress()
        report["nowcoder"] = {
            "queries_total": len(nc_queries_all),
            "queries_run_this_session": len(nc_queries),
            "fetched": len(all_nc),
            "meta_summary": {
                "count": len(all_nc),
                "per_query_errors": [r.get("error") for r in per_query_meta if r.get("error")],
            },
        }
        report["stages"]["nowcoder_fetched"] = _stage_counts(all_nc, role_label, recency_days)
        print(f"  牛客合计 {len(all_nc)} 篇（补充源）", flush=True)

    rolling_path = rolling_nowcoder_path()
    if rolling_path.is_file():
        rolling_posts = [
            RawPost.from_dict(d)
            for d in json.loads(rolling_path.read_text(encoding="utf-8"))
        ]
        report["stages"]["rolling_file"] = _stage_counts(rolling_posts, role_label, recency_days)

    if not args.no_rebuild:
        print("重建面经库 …")
        fast_rebuild = args.fast_rebuild or (args.skip_xhs and args.skip_nowcoder)
        cfg = RunConfig(
            role=role_label,
            role_id=role_id,
            companies=companies,
            refresh=True,
            discover_nowcoder=False,
            xhs_use_export=True,
            xhs_priority=True,
            xhs_deep=not fast_rebuild,
            xhs_live=False,
            recency_window_days=recency_days,
            skip_role_filter=skip_role_filter,
            skip_rolling_nowcoder=args.skip_nowcoder,
        )
        try:
            result = run_pipeline(cfg)
            report["bank"] = {
                "slug": result.slug,
                "post_count": result.post_count,
                "question_count": result.ranked_count,
                "sources": result.sources,
            }
            print(f"  面经库 {result.post_count} 篇 / {result.ranked_count} 题")
        except Exception as exc:  # noqa: BLE001
            report["bank"]["error"] = str(exc)
            print(f"  建库失败: {exc}")

    report_path = Path("corpus_cache/daily/full_scrape_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n--- 漏斗 ---")
        for name, block in report.get("stages", {}).items():
            if isinstance(block, dict):
                print(
                    f"  {name}: raw={block.get('raw')} "
                    f"→ role={block.get('after_role_filter')} "
                    f"→ recency({block.get('recency_days')}d)={block.get('after_recency')}"
                )
        print(f"报告: {report_path}")

    if report.get("bank", {}).get("error"):
        return 1
    if report.get("xhs", {}).get("error") and not args.skip_xhs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
