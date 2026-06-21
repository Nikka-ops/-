#!/usr/bin/env python3
"""大批量拉取面经 + 在招 JD（CLI，适合长时间跑）。"""
from __future__ import annotations

import argparse
import json

from scripts.config import jobs_dir
from scripts.jobs.service import JobFetchConfig, fetch_jobs
from scripts.corpus.company_catalog import resolve_company_list
from scripts.service import RunConfig, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InterviewRadar 大批量抓取")
    parser.add_argument("--role-id", default="ai_app")
    parser.add_argument("--role", default="")
    parser.add_argument(
        "--companies",
        nargs="*",
        default=["字节跳动", "腾讯", "阿里巴巴", "美团"],
        help="公司列表；传 all 表示全国大厂预设",
    )
    parser.add_argument("--discover-max", type=int, default=50, help="每个搜索词最多牛客条数")
    parser.add_argument("--jobs-max", type=int, default=100, help="每个来源/关键词 JD 上限")
    parser.add_argument("--no-jobs", action="store_true")
    parser.add_argument("--no-posts", action="store_true")
    parser.add_argument("--boss-cdp", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    companies = resolve_company_list(list(args.companies))

    out: dict = {}

    if not args.no_posts:
        cfg = RunConfig(
            role=args.role,
            role_id=args.role_id,
            companies=companies,
            refresh=True,
            discover_nowcoder=True,
            discover_max_per_query=args.discover_max,
        )
        result = run_pipeline(cfg)
        out["bank"] = {
            "slug": result.slug,
            "post_count": result.post_count,
            "question_count": result.ranked_count,
            "sources": result.sources,
        }

    if not args.no_jobs:
        jcfg = JobFetchConfig(
            role=args.role,
            role_id=args.role_id,
            companies=companies,
            max_per_query=args.jobs_max,
            job_pro_scope="all",
            job_pro_details=True,
            boss_cdp=args.boss_cdp,
            cache_dir=str(jobs_dir()),
        )
        jresult = fetch_jobs(jcfg, jobs_dir())
        out["jobs"] = {
            "slug": jresult.slug,
            "job_count": jresult.job_count,
            "sources": jresult.sources,
            "warnings": jresult.warnings,
        }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if "bank" in out:
            print(f"面经: {out['bank']['post_count']} 篇, 题库 {out['bank']['question_count']} 题")
        if "jobs" in out:
            print(f"在招 JD: {out['jobs']['job_count']} 个")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
