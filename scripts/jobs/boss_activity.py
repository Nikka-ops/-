"""Parse Boss 招聘者活跃/回复状态（来自 detail.json，非 joblist 搜索参数）。"""
from __future__ import annotations

from scripts.jobs.models import JobPosting

# 分数越高越「新鲜」；用于过滤僵尸岗
_ACTIVITY_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("刚刚活跃", "刚刚在线", "在线")),
    (4, ("今日回复", "今日活跃", "今天活跃", "24小时")),
    (3, ("近一周", "近一周内", "本周活跃", "一周内", "7天")),
    (2, ("本月活跃", "30天", "近一个月")),
)


def parse_boss_activity_from_detail(payload: dict) -> dict[str, str | bool]:
    """Extract boss activity fields from detail.json (same source as app job page)."""
    if payload.get("code") != 0:
        return {}
    zp = payload.get("zpData") or {}
    boss = zp.get("bossInfo") or {}
    job = zp.get("jobInfo") or {}
    relation = zp.get("relationInfo") or {}

    def _s(val: object) -> str:
        return str(val or "").strip()

    active_desc = _s(
        boss.get("activeTimeDesc")
        or boss.get("activeTimeDescStr")
        or boss.get("activeStatusDesc")
    )
    reply_hint = _s(
        boss.get("replyLevelName")
        or boss.get("replyLevelDesc")
        or boss.get("replyText")
        or boss.get("replyRateDesc")
        or relation.get("replyLevelName")
        or relation.get("replyLevelDesc")
    )
    # App 文案如「今日回复10+」有时在 activeTimeDesc，有时在单独字段
    combined = " ".join(x for x in (active_desc, reply_hint) if x)

    return {
        "boss_active_desc": active_desc,
        "boss_reply_hint": reply_hint,
        "boss_activity_text": combined,
        "boss_online": bool(boss.get("bossOnline")),
        "boss_name": _s(boss.get("name") or boss.get("bossName")),
        "boss_title": _s(boss.get("title") or boss.get("bossTitle")),
        "job_status_desc": _s(job.get("jobStatusDesc")),
    }


def boss_activity_score(text: str) -> int:
    """Map Chinese activity copy to score; 0 = unknown/stale."""
    t = (text or "").strip()
    if not t:
        return 0
    for score, needles in _ACTIVITY_RULES:
        if any(n in t for n in needles):
            return score
    if "活跃" in t:
        return 1
    return 0


def boss_activity_score_from_job(job: JobPosting) -> int:
    extra = job.extra or {}
    text = str(
        extra.get("boss_activity_text")
        or extra.get("boss_active_desc")
        or ""
    ).strip()
    if text:
        return boss_activity_score(text)
    if extra.get("boss_online"):
        return 5
    return 0


def min_score_for_level(level: str) -> int:
    key = (level or "").strip().lower()
    mapping = {
        "online": 5,
        "today": 4,
        "week": 3,
        "month": 2,
        "any": 1,
    }
    if key not in mapping:
        raise ValueError(f"unknown boss activity level: {level}")
    return mapping[key]


def filter_jobs_by_boss_activity(
    jobs: list[JobPosting],
    *,
    min_level: str = "week",
) -> tuple[list[JobPosting], dict]:
    """Keep jobs whose detail-derived boss activity meets min_level."""
    threshold = min_score_for_level(min_level)
    kept: list[JobPosting] = []
    meta = {
        "min_level": min_level,
        "min_score": threshold,
        "before": len(jobs),
        "kept": 0,
        "dropped_no_detail": 0,
        "dropped_inactive": 0,
    }
    for job in jobs:
        score = boss_activity_score_from_job(job)
        if score == 0 and not (job.extra or {}).get("boss_activity_fetched"):
            meta["dropped_no_detail"] += 1
            continue
        if score < threshold:
            meta["dropped_inactive"] += 1
            continue
        meta["kept"] += 1
        kept.append(job)
    return kept, meta


def apply_boss_activity_to_job(job: JobPosting, payload: dict) -> None:
    activity = parse_boss_activity_from_detail(payload)
    if not activity:
        return
    extra = dict(job.extra or {})
    extra.update(activity)
    extra["boss_activity_fetched"] = True
    extra["boss_activity_score"] = boss_activity_score(
        str(activity.get("boss_activity_text") or "")
    )
    job.extra = extra
