#!/usr/bin/env python3
"""PoC: Boss 网页筛完后，按当前 URL 筛选参数拉取 joblist（CDP 短连接）。

用法:
  1. bash scripts/tools/focus-boss-cdp-chrome.sh
  2. 在 CDP Chrome 打开职位页、登录、设筛选（筛选项应反映在地址栏 URL）
  3. 运行本脚本，按提示回车；监听期间在 Chrome 里滚动列表

快速自检:
  .venv/bin/python -m scripts.tools.boss_listen_test --auto --listen-seconds 15
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from scripts.config import boss_cdp_port, bootstrap_env
from scripts.jobs.cdp_client import CdpError, cdp_port_open, find_zhipin_page_ws, open_zhipin_page
from scripts.jobs.enrich import enrich_boss_description
from scripts.jobs.boss_activity import filter_jobs_by_boss_activity
from scripts.jobs.cdp_listen import (
    capture_boss_jobs_via_listen,
    capture_joblist_from_page_filters,
    capture_joblist_payloads,
    capture_joblist_payloads_via_hook,
    jobs_from_joblist_payload,
)


def _activate_cdp_chrome() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Google Chrome" to activate',
        ],
        check=False,
        capture_output=True,
    )


def _jobs_from_payloads(payloads: list[dict]) -> list:
    jobs = []
    seen: set[str] = set()
    for payload in payloads:
        for job in jobs_from_joblist_payload(payload):
            fp = job.fingerprint()
            if fp in seen:
                continue
            seen.add(fp)
            jobs.append(job)
    return jobs


def _enrich_boss_jds(jobs: list, *, port: int, limit: int, delay: float) -> int:
    import time

    enriched = 0
    for job in jobs:
        if enriched >= limit:
            break
        extra = job.extra or {}
        if extra.get("boss_activity_fetched") and (job.description or "").strip():
            continue
        if enrich_boss_description(job, port=port):
            enriched += 1
            if delay > 0:
                time.sleep(delay)
    return enriched


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="Boss CDP listen joblist PoC")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="不等待人工筛选，自动打开页并触发搜索（验证链路）",
    )
    parser.add_argument(
        "--network",
        action="store_true",
        help="交互模式用 CDP Network 长连接（易断连，仅调试）",
    )
    parser.add_argument(
        "--hook",
        action="store_true",
        help="交互模式用页面 hook + 手动滚动（筛选项不在 URL 时用）",
    )
    parser.add_argument("--listen-seconds", type=float, default=30.0)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument(
        "--with-details",
        action="store_true",
        help="逐条拉 detail.json 补全岗位 JD（较慢，建议配合 --detail-limit）",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=20,
        help="最多补全几条 JD（默认 20）",
    )
    parser.add_argument(
        "--min-boss-active",
        choices=("week", "today", "online", "month", "any"),
        default="",
        help="按 detail.json 的 Boss 活跃文案过滤（需 --with-details）",
    )
    parser.add_argument("--scroll-times", type=int, default=3)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    port = args.port or boss_cdp_port()
    if not cdp_port_open(port):
        print("✗ CDP 未启动。请先运行:", file=sys.stderr)
        print("  bash scripts/tools/focus-boss-cdp-chrome.sh", file=sys.stderr)
        return 1

    if not args.auto:
        print("=" * 60)
        print("Boss 筛选拉取 PoC")
        print("")
        print("1. bash scripts/tools/focus-boss-cdp-chrome.sh  # 聚焦专用 Chrome")
        print("2. 登录 Boss，设筛选，确认地址栏 URL 含 city/query 等参数")
        print("3. 回终端按回车 → 按当前 URL 参数直接拉 joblist（无需滚动）")
        print("   若筛选项不在 URL：加 --hook，按回车后手动滚动列表")
        print("=" * 60)
        try:
            input("\n>>> 筛选完成后按回车开始拉取… ")
        except EOFError:
            print("非交互环境请使用 --auto", file=sys.stderr)
            return 1

    try:
        if args.auto:
            jobs, meta = capture_boss_jobs_via_listen(
                port=port,
                listen_seconds=args.listen_seconds,
                trigger_search=True,
                scroll_times=max(0, args.scroll_times),
            )
            payloads_count = meta.get("payload_count", 0)
        elif args.network:
            page_ws = find_zhipin_page_ws(port) or open_zhipin_page(port)
            if not page_ws:
                print("✗ 未找到 Boss 页面标签", file=sys.stderr)
                return 1
            _activate_cdp_chrome()
            payloads = capture_joblist_payloads(
                page_ws,
                port=port,
                listen_seconds=args.listen_seconds,
                trigger_search=False,
                scroll_times=max(0, args.scroll_times),
            )
            jobs = _jobs_from_payloads(payloads)
            meta = {"capture_mode": "network", "payload_count": len(payloads)}
            payloads_count = len(payloads)
        elif args.hook:
            if not find_zhipin_page_ws(port):
                open_zhipin_page(port)
            print("")
            print(f">>> hook 监听 {args.listen_seconds:.0f}s：请切到 CDP Chrome 向下滚动列表")
            print("")
            _activate_cdp_chrome()
            payloads = capture_joblist_payloads_via_hook(
                port=port,
                listen_seconds=args.listen_seconds,
            )
            jobs = _jobs_from_payloads(payloads)
            meta = {"capture_mode": "hook", "payload_count": len(payloads)}
            payloads_count = len(payloads)
        else:
            payloads, meta = capture_joblist_from_page_filters(
                port=port,
                max_pages=max(1, args.max_pages),
            )
            jobs = _jobs_from_payloads(payloads)
            meta = {
                **meta,
                "payload_count": len(payloads),
                "job_count": len(jobs),
                "port": port,
                "mode": "interactive",
            }
            payloads_count = len(payloads)
    except CdpError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if not args.auto:
            print("  先运行: bash scripts/tools/focus-boss-cdp-chrome.sh", file=sys.stderr)
            print("  若筛选项不在 URL，试: --hook 并按回车后滚动列表", file=sys.stderr)
        return 1

    if args.auto:
        payloads_count = meta.get("payload_count", 0)

    detail_enriched = 0
    activity_meta: dict = {}
    if args.min_boss_active and not args.with_details:
        print("✗ --min-boss-active 需配合 --with-details（活跃状态在 detail.json）", file=sys.stderr)
        return 1
    if args.with_details and jobs:
        limit = max(1, args.detail_limit)
        print(f"\n>>> 拉 detail.json（最多 {limit} 条，含 JD + Boss 活跃状态）…")
        detail_enriched = _enrich_boss_jds(
            jobs,
            port=port,
            limit=limit,
            delay=max(0.0, args.detail_delay),
        )

    if args.min_boss_active and jobs:
        jobs, activity_meta = filter_jobs_by_boss_activity(
            jobs, min_level=args.min_boss_active
        )

    with_jd = sum(1 for j in jobs if (j.description or "").strip())
    with_activity = sum(
        1 for j in jobs if (j.extra or {}).get("boss_activity_fetched")
    )

    report = {
        **meta,
        "ok": len(jobs) > 0,
        "job_count": len(jobs),
        "with_jd_count": with_jd,
        "with_activity_count": with_activity,
        "detail_enriched": detail_enriched,
        "activity_filter": activity_meta or None,
        "sample": [
            {
                "title": j.title,
                "company": j.company,
                "city": j.city,
                "salary": j.salary,
                "url": j.url,
                "boss_active": (j.extra or {}).get("boss_active_desc"),
                "boss_reply": (j.extra or {}).get("boss_reply_hint"),
                "description_preview": (j.description or "")[:120],
            }
            for j in jobs[:5]
        ],
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("")
        if jobs:
            mode = meta.get("capture_mode", meta.get("mode", "?"))
            print(f"✓ 可行（{mode}）：截到 {payloads_count} 次 joblist，解析 {len(jobs)} 条岗位")
            if args.with_details or with_jd:
                print(f"  含 JD 正文: {with_jd}/{len(jobs)}")
            if with_activity:
                print(f"  含 Boss 活跃状态: {with_activity}/{len(jobs)}")
            if activity_meta:
                print(
                    f"  活跃过滤({activity_meta.get('min_level')}): "
                    f"保留 {activity_meta.get('kept')}，"
                    f"剔除 inactive {activity_meta.get('dropped_inactive')}，"
                    f"无 detail {activity_meta.get('dropped_no_detail')}"
                )
            if meta.get("page_url"):
                print(f"  页面: {meta['page_url'][:100]}")
            for j in jobs[:5]:
                line = f"  · {j.title} | {j.company} | {j.city or '-'} | {j.salary or '-'}"
                print(line)
                act = (j.extra or {}).get("boss_active_desc") or ""
                reply = (j.extra or {}).get("boss_reply_hint") or ""
                if act or reply:
                    print(f"    Boss: {act}{(' | ' + reply) if reply else ''}")
                if (j.description or "").strip():
                    preview = j.description.replace("\n", " ")[:80]
                    print(f"    JD: {preview}…")
            if len(jobs) > 5:
                print(f"  … 另有 {len(jobs) - 5} 条")
            if not args.with_details and with_jd < len(jobs):
                print(
                    "  提示: joblist 无完整 JD/Boss 活跃；"
                    "加 --with-details --min-boss-active week"
                )
        else:
            print("✗ 未拉到岗位")
            print("  检查: CDP Chrome 已登录？URL 含筛选参数？")
            print("  试: --hook 或 --auto")

    return 0 if jobs else 1


if __name__ == "__main__":
    raise SystemExit(main())
