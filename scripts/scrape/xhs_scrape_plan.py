"""Plan XHS keyword batches (shared by CLI, Web API, incremental)."""
from __future__ import annotations

from scripts.config import xhs_batch_pause_seconds, xhs_daily_keywords_per_day
from scripts.scrape.keywords import xhs_core_keywords_for_role, xhs_keywords_for_role
from scripts.scrape.scrape_state import load_scrape_state, pick_xhs_keyword_batch, save_scrape_state


def plan_xhs_scrape_batch(
    role_id: str,
    companies: list[str],
    *,
    explicit_keywords: list[str] | None = None,
    core_only: bool = False,
    aggressive: bool = False,
    keywords_per_day: int = 0,
    rotate: bool = True,
) -> tuple[list[str], float, int, dict]:
    """Return (keywords, pause_seconds, batch_size, meta)."""
    if explicit_keywords:
        batch = [k.strip() for k in explicit_keywords if k and k.strip()]
        meta = {"mode": "explicit", "pool_size": len(batch)}
        pause = 12.0 if aggressive else xhs_batch_pause_seconds()
        return batch, pause, 3 if aggressive else 2, meta

    pool = (
        xhs_core_keywords_for_role(role_id)
        if core_only
        else xhs_keywords_for_role(role_id, companies)
    )
    per_day = keywords_per_day or (
        len(pool) if core_only else xhs_daily_keywords_per_day()
    )
    pause = 12.0 if aggressive else xhs_batch_pause_seconds()
    batch_size = 3 if aggressive else 2

    if rotate and per_day > 0:
        state = load_scrape_state()
        batch = pick_xhs_keyword_batch(pool, state, per_day=max(1, per_day))
        save_scrape_state(state)
        meta = {
            "mode": "core_only" if core_only else "full",
            "pool_size": len(pool),
            "keywords_per_day": per_day,
            "rotated": True,
        }
    else:
        batch = pool[: max(1, per_day)] if per_day else list(pool)
        meta = {
            "mode": "core_only" if core_only else "full",
            "pool_size": len(pool),
            "keywords_per_day": per_day,
            "rotated": False,
        }
    return batch, pause, batch_size, meta
