"""小红书温和批量抓取 — 单轮 35 词(带抖动),供计划任务每 4 小时调用一次。

scrape_state 记录已抓关键词，每轮自动取「最久未抓」的一批，2-3 天轮转覆盖全量。
遇验证码/风控立即停当轮（保留已抓），下一轮继续。抓完 --import-only 交给日常重建。
"""
from __future__ import annotations

import json
import sys
from datetime import date

from scripts.config import bootstrap_env
from scripts.corpus.company_catalog import resolve_company_list
from scripts.corpus.tech_roles import resolve_role_label
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.scrape_health import NEXT_STEP_XHS_AUTH, record
from scripts.scrape.scrape_state import load_scrape_state, save_scrape_state
from scripts.scrape.xhs_export import run_safe_xhs_scrape

_BATCH = 35  # 单轮词数（实测 30 内安全，35 留少量余量）


def _next_keywords(state: dict, role_id: str, pool: list[str], n: int) -> list[str]:
    """取最久未抓的 n 个关键词（round-robin 覆盖全量）。"""
    seen: dict = state.setdefault("xhs_kw_last", {}).setdefault(role_id, {})
    ranked = sorted(pool, key=lambda k: seen.get(k, ""))  # 空串（从未抓）排最前
    return ranked[:n]


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    role_id = (argv[0] if argv else "data").strip() or "data"
    role_label = resolve_role_label(role_id=role_id)
    companies = resolve_company_list("all")
    pool = xhs_keywords_for_role(role_id, companies)

    state = load_scrape_state()
    batch = _next_keywords(state, role_id, pool, _BATCH)
    if not batch:
        print("关键词池为空"); return 0

    print(f"[{role_label}] 本轮 {len(batch)}/{len(pool)} 词（温和抖动节奏）", flush=True)
    try:
        out = run_safe_xhs_scrape(batch, batch_size=2, limit_keywords=False)
        # 标记这批已抓（时间戳）
        now = date.today().isoformat()
        for k in batch:
            state["xhs_kw_last"][role_id][k] = now
        save_scrape_state(state)
        record("xiaohongshu", status="ok", detail=f"{role_label} 批量 {len(batch)} 词",
               count=int(out.get("note_count") or 0))
        print(f"导出 → {out.get('export_path')} · driver={out.get('driver')}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        auth = any(m in msg for m in ("验证", "登录", "过期", "风控", "461"))
        record("xiaohongshu", status="risk_control" if auth else "error",
               detail=msg[:200], next_step=NEXT_STEP_XHS_AUTH if auth else "")
        print(f"本轮中止（不影响下轮）: {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
