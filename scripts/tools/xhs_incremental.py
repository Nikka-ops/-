#!/usr/bin/env python3
"""小红书长期增量：抓 JSON → 本地导出入库。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from scripts.corpus.company_catalog import resolve_company_list
from scripts.corpus.tech_roles import resolve_role_label
from scripts.config import (
    bootstrap_env,
    full_scrape_recency_days,
    xhs_export_max_age_days,
    xhs_web_session_configured,
)
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.scrape_state import (
    collect_note_ids_from_export_files,
    load_scrape_state,
    register_xhs_note_ids,
    save_scrape_state,
)
from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError, _HTTP_461_HINT
from scripts.scrape.xhs_export import collect_xhs_export_files, run_safe_xhs_scrape
from scripts.scrape.xhs_scrape_plan import plan_xhs_scrape_batch
from scripts.tools.daily_scrape import _rebuild_bank


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="小红书长期增量（抓 JSON + 本地入库）")
    parser.add_argument("--role-id", default="data")
    parser.add_argument("--companies", default="all")
    parser.add_argument("--core-only", action="store_true", help="仅 26 个核心词")
    parser.add_argument("--aggressive", action="store_true", help="更短批间间隔")
    parser.add_argument("--keywords-per-day", type=int, default=0)
    parser.add_argument("--import-only", action="store_true")
    parser.add_argument("--scrape-only", action="store_true")
    parser.add_argument("--fast-rebuild", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    companies = resolve_company_list(args.companies)
    role_id = args.role_id.strip()
    role_label = resolve_role_label(role_id=role_id)
    from scripts.scrape.keywords import xhs_core_keywords_for_role, xhs_keywords_for_role

    pool_size = len(
        xhs_core_keywords_for_role(role_id)
        if args.core_only
        else xhs_keywords_for_role(role_id, companies)
    )

    state = load_scrape_state()
    report: dict = {
        "date": date.today().isoformat(),
        "role_id": role_id,
        "role": role_label,
        "xhs": {"keyword_pool": pool_size},
        "bank": {},
    }

    if not args.import_only:
        batch, pause, batch_size, plan_meta = plan_xhs_scrape_batch(
            role_id,
            companies,
            core_only=args.core_only,
            aggressive=args.aggressive,
            keywords_per_day=args.keywords_per_day,
        )
        report["xhs"]["plan"] = plan_meta
        report["xhs"]["keywords_today"] = batch
        if not xhs_web_session_configured():
            report["xhs"]["error"] = "Cookie 未配置"
            print("Cookie 未配置 — bash scripts/tools/start-xhs-cdp-chrome.sh", file=sys.stderr)
        elif batch:
            est_min = max(1, int(len(batch) * pause / batch_size / 60))
            print(f"抓取 {len(batch)} 词 · 批 {batch_size} · 间隔 {pause}s · 约 {est_min} 分钟")
            from scripts.scrape.scrape_health import NEXT_STEP_XHS_AUTH, record
            try:
                out = run_safe_xhs_scrape(
                    batch,
                    batch_size=batch_size,
                    pause_seconds=pause,
                    limit_keywords=not args.core_only,
                )
                report["xhs"].update(out)
                print(f"导出 → {out.get('export_path')}")
                record("xiaohongshu", status="ok", detail="抓取成功",
                       count=int(out.get("note_count") or 0))
            except SpiderXHSScrapeError as exc:
                report["xhs"]["error"] = str(exc)
                print(f"抓取失败: {exc}", file=sys.stderr)
                auth = any(m in str(exc) for m in ("登录", "过期", "风控", "461"))
                record(
                    "xiaohongshu",
                    status="auth_expired" if auth else "error",
                    detail=str(exc)[:200],
                    next_step=NEXT_STEP_XHS_AUTH if auth else "",
                )
        paths = collect_xhs_export_files(max_age_days=xhs_export_max_age_days())
        report["xhs"]["note_ids_registered"] = register_xhs_note_ids(
            state,
            collect_note_ids_from_export_files(paths),
        )
        save_scrape_state(state)

    if not args.scrape_only:
        print(f"重建面经库 · {role_label} · 近 {full_scrape_recency_days()} 天 …")
        report["bank"] = _rebuild_bank(
            role_id=role_id,
            role_label=role_label,
            companies=companies,
            fast_rebuild=args.fast_rebuild,
        )
        bank = report["bank"]
        if bank.get("error"):
            print(f"建库失败: {bank['error']}", file=sys.stderr)
        else:
            print(f"完成 {bank.get('post_count', 0)} 篇 / {bank.get('question_count', 0)} 题")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    bank = report.get("bank") or {}
    if bank.get("post_count"):
        return 0
    if args.scrape_only and not report.get("xhs", {}).get("error"):
        return 0
    if args.import_only and bank.get("error"):
        return 1
    if "461" in str(report.get("xhs", {}).get("error", "")):
        print(_HTTP_461_HINT, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
