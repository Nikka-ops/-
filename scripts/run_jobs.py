#!/usr/bin/env python3
"""Fetch open job postings (JD) from Boss直聘 and company career sites."""
from __future__ import annotations

import argparse
import json

from scripts.config import jobs_dir
from scripts.jobs.service import JobFetchConfig, fetch_jobs, list_job_snapshots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="InterviewRadar — 拉取 Boss直聘 / 大厂官网在招岗位 JD",
    )
    parser.add_argument("--role", default="", help="目标岗位文本")
    parser.add_argument("--role-id", default="", help="预设岗位 id，如 ai_app、backend")
    parser.add_argument("--companies", nargs="*", default=[], help="目标公司，如 字节跳动 腾讯")
    parser.add_argument("--cities", nargs="*", default=[], help="城市，如 北京 上海")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=[],
        help="指定来源 id：boss_zhipin bytedance（默认按公司自动选择 + Boss）",
    )
    parser.add_argument("--keywords", nargs="*", default=[], help="自定义搜索词（覆盖 role 生成）")
    parser.add_argument("--max-per-query", type=int, default=100, help="每个来源/关键词最多条数")
    parser.add_argument(
        "--no-boss",
        action="store_true",
        help="不拉 Boss直聘（仅官方招聘站）",
    )
    parser.add_argument(
        "--boss-cdp",
        action="store_true",
        help="Boss 直聘优先用 Chrome CDP（无需 Cookie，需 start-boss-cdp-chrome.sh）",
    )
    parser.add_argument(
        "--no-job-pro",
        action="store_true",
        help="不用开源 job-pro，仅用内置连接器",
    )
    parser.add_argument(
        "--job-pro-scope",
        default="social",
        choices=("social", "campus", "intern", "all"),
        help="job-pro 招聘渠道（社招/校招/实习）",
    )
    parser.add_argument(
        "--no-job-pro-details",
        action="store_true",
        help="不拉 job-pro 完整 JD 正文（默认会拉取，较慢）",
    )
    parser.add_argument("--cache-dir", default="", help="JD 缓存目录，默认 corpus_cache/jobs")
    parser.add_argument("--list", action="store_true", help="列出已缓存的 JD 快照")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    root = args.cache_dir or str(jobs_dir())

    if args.list:
        rows = list_job_snapshots(root)
        if args.json:
            print(json.dumps({"snapshots": rows}, ensure_ascii=False, indent=2))
        else:
            if not rows:
                print("暂无 JD 缓存。运行 interview-radar-jobs --role-id ai_app 拉取。")
            for row in rows:
                print(
                    f"{row.get('slug')}  jobs={row.get('job_count')}  "
                    f"new={row.get('new_count')}  at={row.get('fetched_at')}"
                )
        return 0

    config = JobFetchConfig(
        role=args.role,
        role_id=args.role_id,
        companies=args.companies,
        cities=args.cities,
        sources=args.sources,
        keywords=args.keywords,
        max_per_query=args.max_per_query,
        include_aggregators=not args.no_boss,
        use_job_pro=not args.no_job_pro,
        job_pro_scope=args.job_pro_scope,
        job_pro_details=not args.no_job_pro_details,
        boss_cdp=args.boss_cdp,
        cache_dir=root,
    )
    result = fetch_jobs(config, root)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"JD snapshot: {result.paths.get('jobs')} ({result.job_count} jobs, {result.new_count} new)")
        for cid, meta in result.sources.items():
            print(f"  [{cid}] {meta.get('status')}: {meta.get('message')}")
        for w in result.warnings:
            print(f"Warning: {w}")
        if not result.job_count:
            print("未拉到岗位。Boss 需配置 BOSS_ZHIPIN_COOKIE；字节官网默认可用。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
