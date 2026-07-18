"""Boss 新鲜抓取(保守参数,带详情)— 风控冷却后使用。

每岗位 2 个关键词 × 15 条,详情限速 5~9s(connector 内置)。
连续失败自动停(connector 内置保险丝)。
"""
from __future__ import annotations

import sys
import time

from scripts.config import bootstrap_env, jobs_dir
from scripts.jobs.connectors.boss_drission import BossDrissionConnector
from scripts.jobs.store import jobs_snapshot_slug, write_snapshot

PLANS = [
    ("数据开发", "data", ["数据开发", "大数据开发"]),
    ("Agent 开发", "ai_app", ["AI应用开发", "大模型应用"]),
]


def main() -> int:
    bootstrap_env()
    from scripts.jobs.cdp_client import cdp_port_open

    if not cdp_port_open(9222):
        print("CDP Chrome (9222) 未启动", file=sys.stderr)
        return 2
    conn = BossDrissionConnector(with_details=True)
    try:
        for role, role_id, queries in PLANS:
            t0 = time.time()
            res = conn.search(queries, city="北京", max_per_query=15)
            jobs = res.jobs
            with_jd = sum(1 for j in jobs if len(j.description or "") > 50)
            if not jobs:
                print(f"[{role}] 0 jobs — 可能仍在风控期,跳过写入", flush=True)
                continue
            slug = jobs_snapshot_slug(role, [], [])
            try:
                write_snapshot(
                    jobs_dir(), slug, jobs,
                    role=role, role_id=role_id, companies=[], cities=["北京"],
                    sources={"boss_drission": {"status": res.status, "count": len(jobs), "with_jd": with_jd}},
                    queries=queries,
                )
            except ValueError as exc:
                print(f"[{role}] snapshot guard: {exc}", flush=True)
                continue
            print(f"[{role}] {len(jobs)} jobs, {with_jd} with JD, {int(time.time()-t0)}s", flush=True)
            time.sleep(30)
    finally:
        conn._page = None  # 不关用户的 Chrome
    print("BOSS DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
