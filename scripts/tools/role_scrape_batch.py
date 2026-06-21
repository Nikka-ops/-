#!/usr/bin/env python3
"""Discover + scrape a few 牛客帖 per preset tech role; write summary report.

用法:
  .venv/bin/python -m scripts.tools.role_scrape_batch
  .venv/bin/python -m scripts.tools.role_scrape_batch --max-per-role 3 --build-banks
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from scripts.corpus.classify import classify_search_queries
from scripts.corpus.ingest_fallback import nonempty_posts
from scripts.corpus.recency import filter_recent
from scripts.corpus.tech_roles import TECH_ROLES
from scripts.connectors.nowcoder import NowCoderConnector
from scripts.discover.nowcoder_moments import search_nowcoder_moments
from scripts.discover.nowcoder_urls import discover_nowcoder_urls
from scripts.service import RunConfig, run_pipeline


def scrape_role(role, *, max_urls: int, delay: float) -> dict:
    queries = classify_search_queries(roles=[role.search_as], companies=None)
    urls, _discover_meta = discover_nowcoder_urls(
        queries[:2],
        max_per_query=max_urls,
        request_delay=delay,
    )
    moment_posts, moment_meta = search_nowcoder_moments(
        queries[:2],
        max_per_query=max_urls,
        request_delay=delay,
    )
    row: dict = {
        "id": role.id,
        "label": role.label,
        "search_as": role.search_as,
        "queries": queries[:2],
        "discovered_urls": urls,
        "discovered_count": len(urls),
        "nowcoder_moments": moment_meta,
        "moment_count": len(moment_posts),
    }
    posts = list(moment_posts)
    if urls:
        nc = NowCoderConnector(post_urls=urls, request_delay=0.8).search(queries)
        row["nowcoder_status"] = nc.status
        row["nowcoder_message"] = nc.message
        row["nowcoder_discuss_count"] = len(nc.posts)
        posts.extend(nc.posts)
    posts = nonempty_posts(posts)
    posts = filter_recent(posts, today=date.today())
    # dedupe by url
    seen: set[str] = set()
    unique: list = []
    for p in posts:
        key = p.url or p.raw_text[:80]
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    posts = unique
    row["post_count"] = len(posts)
    if posts:
        row["status"] = "ok"
        row["sample_title"] = (posts[0].raw_text or "")[:80].replace("\n", " ")
        row["posts"] = [p.to_dict() for p in posts]
    elif row.get("discovered_count", 0) == 0 and row.get("moment_count", 0) == 0:
        row["status"] = "no_results"
        row["message"] = "牛客搜索与 URL 发现均无结果"
        row["posts"] = []
    else:
        row["status"] = "empty_body"
        row["message"] = row.get("nowcoder_message") or "正文为空"
        row["posts"] = []
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch scrape test for all tech roles")
    parser.add_argument("--max-per-role", type=int, default=2, help="Max 牛客 URLs per role query")
    parser.add_argument("--delay", type=float, default=1.2, help="Delay between discover queries (s)")
    parser.add_argument("--out", default="corpus_cache/role_batch_report.json")
    parser.add_argument(
        "--build-banks",
        action="store_true",
        help="Build question banks for roles that scraped successfully",
    )
    parser.add_argument("--cache-dir", default="corpus_cache/banks")
    args = parser.parse_args()

    report: dict = {
        "generated_at": date.today().isoformat(),
        "max_per_role": args.max_per_role,
        "roles": [],
    }

    for i, role in enumerate(TECH_ROLES):
        if i:
            time.sleep(args.delay)
        print(f"[{i + 1}/{len(TECH_ROLES)}] {role.label} …", flush=True)
        row = scrape_role(role, max_urls=args.max_per_role, delay=args.delay)
        if args.build_banks and row.get("posts"):
            try:
                # Save scraped posts to temp report and build bank without fallback
                tmp = Path(args.out).parent / f"role_batch_{role.id}.json"
                tmp.write_text(
                    json.dumps({"queries": row["queries"], "posts": row["posts"]}, ensure_ascii=False),
                    encoding="utf-8",
                )
                result = run_pipeline(
                    RunConfig(
                        role=role.search_as,
                        role_id=role.id,
                        raw_posts=str(tmp),
                        from_report=True,
                        refresh=True,
                        cache_dir=args.cache_dir,
                        agent_handoff=False,
                    )
                )
                row["bank_slug"] = result.slug
                row["question_count"] = result.ranked_count
                row["bank_path"] = result.paths.get("question_bank")
            except Exception as exc:  # noqa: BLE001
                row["build_error"] = str(exc)
        # drop heavy posts from summary unless needed
        if "posts" in row and not args.build_banks:
            del row["posts"]
        elif "posts" in row:
            row["posts_saved"] = len(row["posts"])
            del row["posts"]
        report["roles"].append(row)
        print(
            f"  → {row['status']}: urls={row.get('discovered_count', 0)} posts={row.get('post_count', 0)}",
            flush=True,
        )

    ok = sum(1 for r in report["roles"] if r.get("post_count", 0) > 0)
    report["summary"] = {
        "total_roles": len(TECH_ROLES),
        "roles_with_posts": ok,
        "roles_no_urls": sum(1 for r in report["roles"] if r.get("status") == "no_results"),
        "roles_empty_body": sum(1 for r in report["roles"] if r.get("status") == "empty_body"),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== Summary ===")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Full report: {out}")
    return 0 if ok >= len(TECH_ROLES) // 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
