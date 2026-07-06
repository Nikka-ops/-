"""Assign cluster ids and export ranked question clusters."""
from __future__ import annotations

from scripts.models import Question


def assign_cluster_ids(ranked: list[Question]) -> list[Question]:
    for i, q in enumerate(ranked, start=1):
        q.cluster_id = f"c{i:03d}"
    return ranked


def build_clusters(ranked: list[Question], *, ref_score_fn) -> list[dict]:
    """Ranked clusters: batch_count = 出现批次数 (跨面经帖频次)."""
    clusters: list[dict] = []
    for i, q in enumerate(ranked, start=1):
        score = ref_score_fn(q)
        clusters.append(
            {
                "rank": i,
                "cluster_id": q.cluster_id or f"c{i:03d}",
                "representative": q.text,
                "batch_count": q.freq,
                "score": round(score, 3),
                "topic": q.topic,
                "confidence": _confidence(q.freq),
                "company_tags": q.company_tags,
                "role_tags": q.role_tags,
                "latest_posted_at": q.latest_posted_at,
                "variant_count": len(q.variants),
                "variants": q.variants,
                "source_refs": q.source_refs,
                "answer": q.answer or "",
            }
        )
    return clusters


def _confidence(freq: int) -> str:
    if freq >= 3:
        return "高频"
    if freq == 2:
        return "中频"
    return "低频"
