"""Serialize question bank for Web UI: topic groups, source breakdown, stats."""
from __future__ import annotations

from collections import Counter

from scripts.models import RawPost

_UNKNOWN_TOPIC = "综合"
_CONF_ORDER = {"高频": 0, "中频": 1, "低频": 2}


def ref_source_kind(ref: str) -> str:
    s = (ref or "").strip().lower()
    if "xiaohongshu" in s or "xhs" in s:
        return "xiaohongshu"
    if "nowcoder" in s:
        return "nowcoder"
    return "other"


def ref_source_label(kind: str) -> str:
    if kind == "xiaohongshu":
        return "小红书"
    if kind == "nowcoder":
        return "牛客"
    return "其他"


def _confidence(freq: int) -> str:
    if freq >= 3:
        return "高频"
    if freq == 2:
        return "中频"
    return "低频"


def _posts_by_url(posts: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for row in posts:
        for key in (row.get("url"), row.get("source_url")):
            u = (key or "").strip()
            if u:
                index[u] = row
    return index


def enrich_question_row(q: dict, posts_index: dict[str, dict] | None = None) -> dict:
    row = dict(q)
    refs = [r for r in (row.get("source_refs") or []) if r]
    kinds = Counter(ref_source_kind(r) for r in refs)
    row["source_kinds"] = dict(kinds)
    row["source_labels"] = [ref_source_label(k) for k, n in kinds.items() if n and k != "other"]
    row["confidence"] = row.get("confidence") or _confidence(int(row.get("batch_count") or row.get("freq") or 1))
    row["topic"] = (row.get("topic") or "").strip() or _UNKNOWN_TOPIC
    related: list[dict] = []
    if posts_index:
        seen: set[str] = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            hit = posts_index.get(ref)
            if hit:
                related.append(
                    {
                        "url": hit.get("source_url") or hit.get("url") or ref,
                        "title": hit.get("title") or "面经原文",
                        "source": hit.get("source") or ref_source_kind(ref),
                        "company_label": hit.get("company_label") or hit.get("company") or "",
                        "posted_at": hit.get("posted_at") or "",
                    }
                )
    row["related_posts"] = related[:6]
    return row


def topic_options(questions: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for q in questions:
        counts[q.get("topic") or _UNKNOWN_TOPIC] += 1
    rows = [{"name": name, "count": count} for name, count in counts.items()]
    rows.sort(key=lambda r: (-r["count"], r["name"]))
    if rows and rows[0]["name"] == _UNKNOWN_TOPIC and len(rows) > 1:
        general = rows.pop(0)
        rows.append(general)
    return rows


def bank_stats(questions: list[dict]) -> dict:
    conf = Counter(q.get("confidence") or "低频" for q in questions)
    ref_kinds = Counter()
    for q in questions:
        for kind, n in (q.get("source_kinds") or {}).items():
            ref_kinds[kind] += n
    return {
        "total": len(questions),
        "high": conf.get("高频", 0),
        "medium": conf.get("中频", 0),
        "low": conf.get("低频", 0),
        "xhs_refs": ref_kinds.get("xiaohongshu", 0),
        "nc_refs": ref_kinds.get("nowcoder", 0),
    }


def serialize_question_bank_ui(
    bank: dict | None,
    posts: list[dict] | list[RawPost] | None = None,
) -> dict:
    """Build UI payload from question_bank.json + optional serialized posts."""
    if not bank:
        return {"questions": [], "topics": [], "stats": bank_stats([])}

    post_rows: list[dict] = []
    if posts:
        for p in posts:
            post_rows.append(p if isinstance(p, dict) else p.to_dict())
    posts_index = _posts_by_url(post_rows)

    raw_questions = bank.get("questions") or []
    if not raw_questions and bank.get("clusters"):
        raw_questions = [
            {
                "rank": c.get("rank"),
                "cluster_id": c.get("cluster_id"),
                "text": c.get("representative") or c.get("text") or "",
                "batch_count": c.get("batch_count") or c.get("freq") or 1,
                "topic": c.get("topic"),
                "company_tags": c.get("company_tags") or [],
                "role_tags": c.get("role_tags") or [],
                "variants": c.get("variants") or [],
                "source_refs": c.get("source_refs") or [],
                "answer": c.get("answer") or "",
            }
            for c in bank.get("clusters") or []
        ]

    questions = [enrich_question_row(q, posts_index) for q in raw_questions]
    # Sort by frequency desc; use rank as tiebreaker (rank encodes original pipeline order)
    questions.sort(key=lambda r: (-(r.get("batch_count") or r.get("freq") or 0), r.get("rank") or 9999))
    return {
        "questions": questions,
        "topics": topic_options(questions),
        "stats": bank_stats(questions),
        "role": bank.get("role") or "",
        "post_count": bank.get("post_count") or 0,
        "recency_window_days": bank.get("recency_window_days") or 90,
    }
