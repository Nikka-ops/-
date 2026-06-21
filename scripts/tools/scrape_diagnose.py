#!/usr/bin/env python3
"""Print scrape volume funnel — why post count is low."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from scripts.corpus.company_catalog import all_preset_companies, resolve_company_list
from scripts.corpus.recency import RECENCY_WINDOW_DAYS, filter_recent
from scripts.corpus.role_match import annotate_post, filter_posts_for_bank
from scripts.corpus.tech_roles import resolve_role_label
from scripts.config import bootstrap_env, full_scrape_recency_days, xhs_web_session_configured
from scripts.models import RawPost
from scripts.scrape.keywords import nowcoder_queries_for_role, xhs_keywords_for_role
from scripts.scrape.scrape_state import rolling_nowcoder_path
from scripts.scrape.xhs_export import collect_xhs_export_files, load_xhs_posts_from_exports


def _load_rolling() -> list[RawPost]:
    path = rolling_nowcoder_path()
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RawPost.from_dict(d) for d in raw if isinstance(d, dict)]


def diagnose(role_id: str, companies_raw: str) -> dict:
    companies = resolve_company_list(companies_raw)
    role = resolve_role_label(role_id=role_id)
    nc_q = nowcoder_queries_for_role(role_id, companies)
    xhs_q = xhs_keywords_for_role(role_id, companies)
    full_recency = full_scrape_recency_days()

    rolling = _load_rolling()
    xhs_posts, xhs_meta = load_xhs_posts_from_exports(enable_ocr=False, max_age_days=full_scrape_recency_days())
    merged = rolling + xhs_posts

    ann = [annotate_post(p) for p in merged]
    kept, dropped = filter_posts_for_bank(ann, role)
    kept_skip = ann
    recent_ui = filter_recent(kept, window_days=RECENCY_WINDOW_DAYS)
    recent_full = filter_recent(kept, window_days=full_recency)
    recent_skip = filter_recent(kept_skip, window_days=full_recency)

    return {
        "role": role,
        "role_id": role_id,
        "company_count": len(companies),
        "nowcoder_query_count": len(nc_q),
        "xhs_keyword_count": len(xhs_q),
        "limits": {
            "daily_nowcoder_queries": 24,
            "daily_xhs_keywords": 8,
            "ui_recency_days": RECENCY_WINDOW_DAYS,
            "full_scrape_recency_days": full_recency,
            "xhs_cookie_configured": xhs_web_session_configured(),
            "xhs_export_files": len(collect_xhs_export_files(max_age_days=full_recency)),
            "xhs_export_posts": xhs_meta.get("post_count"),
        },
        "rolling_nowcoder_posts": len(rolling),
        "xhs_import_posts": len(xhs_posts),
        "merged_unique_sources": len(merged),
        "after_strict_role_filter": len(kept),
        "role_filter_dropped": len(dropped),
        "after_recency_ui_90d": len(recent_ui),
        "after_recency_full": len(recent_full),
        "skip_role_filter_full_recency": len(recent_skip),
        "bottlenecks": [
            "daily_scrape 每天只跑 24 个牛客词（全量需 full_scrape：185 词）",
            f"默认 UI 近 {RECENCY_WINDOW_DAYS} 天过滤（全量用 {full_recency} 天）",
            "严格岗位过滤会再少约 25–30%（full_scrape 默认 skip_role_filter）",
            "小红书未配 Cookie 时仅 ~22 条本地 JSON（面经主源缺失）",
        ],
        "recommended_full_scrape": (
            "uv run python -m scripts.tools.full_scrape --role-id "
            f"{role_id} --companies all --skip-xhs"
            + ("" if xhs_web_session_configured() else "  # 配 XHS_WEB_SESSION 后去掉 --skip-xhs")
        ),
    }


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="面经数量漏斗诊断")
    parser.add_argument("--role-id", default="ai_app")
    parser.add_argument("--companies", default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = diagnose(args.role_id, args.companies)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"岗位: {report['role']} · 公司 {report['company_count']} 家")
        print(f"搜索词: 牛客 {report['nowcoder_query_count']} · 小红书 {report['xhs_keyword_count']}")
        print(f"滚动牛客库: {report['rolling_nowcoder_posts']} 篇")
        print(f"小红书导入: {report['xhs_import_posts']} 篇")
        print(f"严格岗位过滤后: {report['after_strict_role_filter']} (丢弃 {report['role_filter_dropped']})")
        print(f"近 90 天(UI默认): {report['after_recency_ui_90d']}")
        print(f"近 {report['limits']['full_scrape_recency_days']} 天(全量): {report['after_recency_full']}")
        print(f"跳过岗位过滤+全量时效: {report['skip_role_filter_full_recency']} ← 全量建库目标量级")
        print("\n主要瓶颈:")
        for b in report["bottlenecks"]:
            print(f"  · {b}")
        print(f"\n推荐全量命令:\n  {report['recommended_full_scrape']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
