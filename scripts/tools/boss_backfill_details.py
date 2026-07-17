"""Boss 直聘 JD 详情限速补全 — 对已有 boss_drission 快照逐岗补正文。

用法（先启动已登录 Boss 的 CDP Chrome，端口 9222）:
    python -m scripts.tools.boss_backfill_details                # 所有 boss 快照，默认每次最多 150 条
    python -m scripts.tools.boss_backfill_details --slug 数据开发_7fa2efaf90 --limit 100

限速：每条详情间隔 5~10 秒随机（Boss 详情页比列表页更易触发 code-37）。
断点续跑：已有正文的岗位自动跳过，每 10 条落盘一次，中断不丢进度。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from scripts.config import bootstrap_env, jobs_dir
from scripts.jobs.connectors.boss_drission import BossDrissionConnector
from scripts.jobs.connectors.boss_zhipin import apply_boss_detail
from scripts.jobs.models import JobPosting

_MIN_PAUSE = 5.0
_MAX_PAUSE = 10.0
_FLUSH_EVERY = 10


def _boss_snapshot_slugs(root: Path) -> list[str]:
    slugs: list[str] = []
    for d in sorted(root.iterdir()):
        jf = d / "jobs.json"
        if not jf.is_file():
            continue
        try:
            rows = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if any((r.get("source") or "").startswith("boss") for r in rows if isinstance(r, dict)):
            slugs.append(d.name)
    return slugs


def _needs_detail(row: dict) -> bool:
    if not (row.get("source") or "").startswith("boss"):
        return False
    if len(row.get("description") or "") > 50:
        return False
    return bool((row.get("extra") or {}).get("security_id"))


def backfill_slug(conn: BossDrissionConnector, root: Path, slug: str, budget: int) -> tuple[int, int]:
    """Returns (filled, consecutive_failures_hit ? -1 : remaining_budget)."""
    jf = root / slug / "jobs.json"
    rows = json.loads(jf.read_text(encoding="utf-8"))
    pending_idx = [i for i, r in enumerate(rows) if _needs_detail(r)]
    if not pending_idx:
        print(f"[{slug}] 无需补全")
        return 0, budget

    print(f"[{slug}] 待补 {len(pending_idx)} 条 · 本轮预算 {budget}")
    filled = 0
    fails = 0
    dirty = False

    def _flush() -> None:
        nonlocal dirty
        if dirty:
            jf.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            dirty = False

    for n, i in enumerate(pending_idx):
        if budget <= 0:
            break
        row = rows[i]
        sid = str((row.get("extra") or {}).get("security_id") or "")
        job = JobPosting.from_dict(row)
        try:
            payload = conn._fetch_detail(sid)  # noqa: SLF001 — tool intentionally reuses connector internals
        except Exception as exc:  # noqa: BLE001
            print(f"  ! detail error: {exc}", file=sys.stderr)
            payload = {}
        budget -= 1
        if payload and isinstance(payload, dict) and payload.get("code") == 0:
            apply_boss_detail(job, payload)
            if len(job.description or "") > 50:
                rows[i] = job.to_dict()
                filled += 1
                fails = 0
                dirty = True
            else:
                fails += 1
        else:
            fails += 1
        if fails >= 5:
            print("  !! 连续 5 次拿不到详情 — 可能触发风控或登录失效，停止本轮", file=sys.stderr)
            _flush()
            return filled, -1
        if filled and filled % _FLUSH_EVERY == 0:
            _flush()
        print(f"  {n+1}/{len(pending_idx)} filled={filled} budget={budget}", end="\r")
        time.sleep(random.uniform(_MIN_PAUSE, _MAX_PAUSE))

    _flush()
    print(f"\n[{slug}] 本轮补全 {filled} 条")
    return filled, budget


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="Boss JD 详情限速补全")
    parser.add_argument("--slug", default="", help="只补指定快照（默认所有含 boss 岗位的快照）")
    parser.add_argument("--limit", type=int, default=150, help="本轮最多请求详情条数（默认 150）")
    args = parser.parse_args(argv)

    from scripts.jobs.cdp_client import cdp_port_open
    if not cdp_port_open(9222):
        print(
            "未检测到 CDP Chrome (9222)。请先启动并登录 Boss：\n"
            '  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
            "--remote-debugging-port=9222 --user-data-dir=C:\\boss-chrome-profile",
            file=sys.stderr,
        )
        return 2

    root = jobs_dir()
    slugs = [args.slug] if args.slug else _boss_snapshot_slugs(root)
    if not slugs:
        print("没有找到含 Boss 岗位的快照")
        return 0

    conn = BossDrissionConnector(with_details=False)
    budget = max(1, args.limit)
    total = 0
    try:
        for slug in slugs:
            filled, budget = backfill_slug(conn, root, slug, budget)
            total += filled
            if budget <= 0:
                break
    finally:
        # 不 quit 接管的用户 Chrome，只断开
        conn._page = None  # noqa: SLF001

    print(f"共补全 {total} 条 JD 正文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
