#!/usr/bin/env python3
"""Daily incremental scrape: Xiaohongshu keyword rotation + Nowcoder new posts.

典型用法（全国大厂 + 数据开发/数仓 + Agent 开发，建议 cron 每天 1 次）:

  uv run python -m scripts.tools.daily_scrape --companies all

显式指定岗位:

  uv run python -m scripts.tools.daily_scrape --role-ids data,ai_app --companies all

环境变量见 .env（XHS_WEB_SESSION、XHS_MAX_KEYWORDS_PER_RUN 等）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from scripts.corpus.company_catalog import resolve_company_list
from scripts.corpus.tech_roles import parse_role_ids, resolve_role_label
from scripts.config import bootstrap_env, full_scrape_recency_days, jobs_dir, nowcoder_daily_queries_per_day, xhs_batch_pause_seconds, xhs_daily_keywords_per_day, xhs_export_max_age_days, xhs_min_posts_skip_nowcoder, xhs_web_session_configured
from scripts.discover.nowcoder_moments import search_nowcoder_moments
from scripts.scrape.keywords import merged_nowcoder_queries_for_roles, merged_xhs_keywords_for_roles
from scripts.scrape.scrape_state import (
    append_rolling_nowcoder_posts,
    collect_note_ids_from_export_files,
    filter_new_nowcoder_posts,
    load_scrape_state,
    pick_nowcoder_query_batch,
    pick_xhs_keyword_batch,
    register_xhs_note_ids,
    save_scrape_state,
)
from scripts.scrape.xhs_export import collect_xhs_export_files, run_safe_xhs_scrape
from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError
from scripts.jobs.service import JobFetchConfig, fetch_jobs_multi
from scripts.corpus.ai_gate import clear_agent_caches
from scripts.service import RunConfig, run_pipeline


def _rebuild_bank(
    *,
    role_id: str,
    role_label: str,
    companies: list[str],
    fast_rebuild: bool,
) -> dict:
    cfg = RunConfig(
        role=role_label,
        role_id=role_id,
        companies=companies,
        refresh=True,
        discover_nowcoder=False,
        xhs_use_export=True,
        xhs_priority=True,
        xhs_min_posts_skip_nowcoder=xhs_min_posts_skip_nowcoder(),
        xhs_deep=not fast_rebuild,
        xhs_live=False,
        recency_window_days=full_scrape_recency_days(),
        skip_role_filter=False,
    )
    try:
        result = run_pipeline(cfg)
        return {
            "role_id": role_id,
            "role": role_label,
            "slug": result.slug,
            "post_count": result.post_count,
            "question_count": result.ranked_count,
        }
    except Exception as exc:  # noqa: BLE001
        return {"role_id": role_id, "role": role_label, "error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="InterviewRadar 每日增量抓取（小红书 + 牛客）")
    parser.add_argument("--role-id", default="", help="单岗位 id（与 --role-ids 二选一）")
    parser.add_argument(
        "--role-ids",
        default="",
        help="逗号分隔多岗位；默认 data,ai_app（数据开发/数仓 + Agent 开发）",
    )
    parser.add_argument("--role", default="", help="覆盖岗位文案（可选，仅单岗位时生效）")
    parser.add_argument(
        "--companies",
        default="all",
        help="公司列表，逗号分隔；all=全国大厂预设 32 家",
    )
    parser.add_argument(
        "--xhs-keywords-per-day",
        type=int,
        default=0,
        help=f"每天轮转的小红书词数（0=默认 {xhs_daily_keywords_per_day()}，主源）",
    )
    parser.add_argument(
        "--nowcoder-queries-per-day",
        type=int,
        default=0,
        help=f"每天牛客补充词数（0=默认 {nowcoder_daily_queries_per_day()}）",
    )
    parser.add_argument("--nowcoder-max-per-query", type=int, default=40, help="每个牛客词最多条数")
    parser.add_argument("--xhs-batch-size", type=int, default=2)
    parser.add_argument("--xhs-pause", type=float, default=0, help="批间暂停秒数（0=默认 30）")
    parser.add_argument("--skip-xhs", action="store_true")
    parser.add_argument("--skip-nowcoder", action="store_true")
    parser.add_argument("--no-rebuild", action="store_true", help="只抓取，不重建面经库")
    parser.add_argument("--skip-jobs", action="store_true", help="不拉在招 JD")
    parser.add_argument(
        "--fast-rebuild",
        action="store_true",
        help="重建时跳过深度 OCR（更快；仅重建时默认开启）",
    )
    parser.add_argument(
        "--clear-ai-cache",
        action="store_true",
        help="重建前清空 Agent 面经/解答缓存（全量重判，较慢）",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    companies = resolve_company_list(args.companies)
    role_ids = parse_role_ids(args.role_id, args.role_ids)
    primary_role_id = role_ids[0]

    state = load_scrape_state()
    state["role_id"] = primary_role_id
    state["role_ids"] = role_ids
    state["companies"] = companies
    report: dict = {
        "date": date.today().isoformat(),
        "role_id": primary_role_id,
        "role_ids": role_ids,
        "role": resolve_role_label(role_id=primary_role_id, role_text=args.role.strip() or None),
        "company_count": len(companies),
        "xhs": {},
        "nowcoder": {},
        "bank": {},
        "banks": [],
        "jobs": {},
    }

    xhs_keywords = merged_xhs_keywords_for_roles(role_ids, companies)
    nowcoder_queries = merged_nowcoder_queries_for_roles(role_ids, companies)
    report["xhs_keyword_total"] = len(xhs_keywords)
    report["nowcoder_query_total"] = len(nowcoder_queries)

    xhs_per_day = args.xhs_keywords_per_day or xhs_daily_keywords_per_day()
    nc_per_day = args.nowcoder_queries_per_day if args.nowcoder_queries_per_day > 0 else nowcoder_daily_queries_per_day()
    xhs_pause = args.xhs_pause or xhs_batch_pause_seconds()

    if not args.skip_xhs:
        batch = pick_xhs_keyword_batch(
            xhs_keywords,
            state,
            per_day=max(1, xhs_per_day),
        )
        report["xhs"]["keywords_per_day"] = xhs_per_day
        report["xhs"]["keywords_today"] = batch
        report["xhs"]["queue_offset_after"] = state.get("xhs_queue_offset")
        if not xhs_web_session_configured():
            report["xhs"]["error"] = "XHS_WEB_SESSION not configured"
            print("小红书未配置 XHS_WEB_SESSION — 面经主源不可用", file=sys.stderr)
        elif not batch:
            report["xhs"]["skipped"] = "no keywords"
        else:
            try:
                out = run_safe_xhs_scrape(
                    batch,
                    batch_size=max(1, args.xhs_batch_size),
                    pause_seconds=max(10.0, xhs_pause),
                )
                report["xhs"]["export_path"] = out.get("export_path")
                report["xhs"]["keywords_run"] = out.get("keywords")
            except (SpiderXHSScrapeError, FileNotFoundError, ValueError) as exc:
                report["xhs"]["error"] = str(exc)
        export_paths = collect_xhs_export_files(max_age_days=xhs_export_max_age_days())
        new_ids = collect_note_ids_from_export_files(export_paths)
        report["xhs"]["note_ids_registered"] = register_xhs_note_ids(state, new_ids)

    if not args.skip_nowcoder and nc_per_day > 0:
        batch_q = pick_nowcoder_query_batch(
            nowcoder_queries,
            state,
            per_day=max(1, nc_per_day),
        )
        report["nowcoder"]["queries_per_day"] = nc_per_day
        report["nowcoder"]["queries_today"] = batch_q
        if batch_q:
            posts, meta = search_nowcoder_moments(
                batch_q,
                max_per_query=max(5, args.nowcoder_max_per_query),
            )
            new_posts = filter_new_nowcoder_posts(posts, state)
            rolled = append_rolling_nowcoder_posts(new_posts)
            report["nowcoder"]["fetched"] = len(posts)
            report["nowcoder"]["new_posts"] = len(new_posts)
            report["nowcoder"]["rolled_total_added"] = rolled
            report["nowcoder"]["meta"] = meta
        else:
            report["nowcoder"]["skipped"] = "no queries"

    state["last_daily_run"] = date.today().isoformat()
    state_path = save_scrape_state(state)
    report["state_path"] = str(state_path)

    if not args.no_rebuild:
        if args.clear_ai_cache:
            cleared = clear_agent_caches()
            report["ai_cache_cleared"] = cleared
        fast_rebuild = args.fast_rebuild or (args.skip_xhs and args.skip_nowcoder)
        banks: list[dict] = []
        for rid in role_ids:
            role_label = resolve_role_label(
                role_id=rid,
                role_text=args.role.strip() or None if len(role_ids) == 1 else None,
            )
            banks.append(
                _rebuild_bank(
                    role_id=rid,
                    role_label=role_label,
                    companies=companies,
                    fast_rebuild=fast_rebuild,
                )
            )
        report["banks"] = banks
        if len(banks) == 1:
            report["bank"] = banks[0]
        elif banks:
            report["bank"] = {
                "role_count": len(banks),
                "post_count": sum(b.get("post_count") or 0 for b in banks),
                "question_count": sum(b.get("question_count") or 0 for b in banks),
            }

    if not args.skip_jobs:
        try:
            jresult = fetch_jobs_multi(
                JobFetchConfig(companies=companies, cache_dir=str(jobs_dir())),
                role_ids,
                jobs_dir(),
            )
            report["jobs"] = {
                "job_count": jresult.job_count,
                "new_count": jresult.new_count,
                "slug": jresult.slug,
                "warnings": jresult.warnings[:5],
            }
        except Exception as exc:  # noqa: BLE001
            report["jobs"] = {"error": str(exc)}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        parts = [
            f"每日增量 {report['date']} · {len(role_ids)} 岗位 · {len(companies)} 家公司",
        ]
        if report.get("xhs", {}).get("keywords_run"):
            parts.append(f"小红书 {len(report['xhs']['keywords_run'])} 词")
        if report.get("nowcoder", {}).get("new_posts"):
            parts.append(f"牛客新增 {report['nowcoder']['new_posts']} 篇")
        banks = report.get("banks") or ([report["bank"]] if report.get("bank") else [])
        for bank in banks:
            if bank.get("post_count"):
                label = bank.get("role_id") or bank.get("role") or "bank"
                parts.append(f"{label} {bank['post_count']} 篇")
        if report.get("jobs", {}).get("job_count"):
            parts.append(f"JD {report['jobs']['job_count']} 个")
        if report.get("xhs", {}).get("error"):
            parts.append(f"小红书: {report['xhs']['error']}")
        for bank in banks:
            if bank.get("error"):
                parts.append(f"建库 {bank.get('role_id', '?')}: {bank['error']}")
        print(" · ".join(parts))

    banks = report.get("banks") or ([report["bank"]] if report.get("bank") else [])
    bank_errs = [b.get("error") for b in banks if b.get("error")]
    xhs_err = report.get("xhs", {}).get("error")
    has_posts = any(b.get("post_count") for b in banks)
    has_hard_error = bool(bank_errs) or (
        bool(xhs_err)
        and not args.skip_xhs
        and not has_posts
        and "461" not in str(xhs_err)
    )
    return 1 if has_hard_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
