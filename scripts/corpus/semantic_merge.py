"""Merge near-duplicate questions by token similarity before freq ranking.

Uses rapidfuzz (token_set_ratio) instead of hand-rolled Jaccard — same semantics,
faster implementation, already battle-tested.
"""
from __future__ import annotations

from rapidfuzz.fuzz import token_set_ratio

from scripts.corpus.dedupe_rank import _max_date, _union
from scripts.models import Question


def similarity(a: str, b: str) -> float:
    """Return [0, 1] similarity using rapidfuzz token_set_ratio."""
    return token_set_ratio(a, b) / 100.0


def _append_variant(into: Question, text: str) -> None:
    t = text.strip()
    if not t or t == into.text or t in into.variants:
        return
    into.variants.append(t)


def merge_similar_questions(
    questions: list[Question],
    *,
    threshold: float = 0.72,
) -> list[Question]:
    """Greedy cluster merge; keeps the shorter text as canonical surface form."""
    clusters: list[Question] = []
    for q in questions:
        best_idx, best_sim = -1, 0.0
        for i, rep in enumerate(clusters):
            sim = similarity(q.text, rep.text)
            if sim > best_sim:
                best_sim, best_idx = sim, i
        if best_idx >= 0 and best_sim >= threshold:
            rep = clusters[best_idx]
            _append_variant(rep, q.text)
            rep.freq += q.freq
            rep.latest_posted_at = _max_date(rep.latest_posted_at, q.latest_posted_at)
            _union(rep.source_refs, q.source_refs)
            _union(rep.role_tags, q.role_tags)
            _union(rep.company_tags, q.company_tags)
            if len(q.text) < len(rep.text):
                _append_variant(rep, rep.text)
                rep.text = q.text
            if not rep.topic or rep.topic == "综合":
                rep.topic = q.topic
        else:
            clusters.append(
                Question(
                    text=q.text,
                    source_refs=list(q.source_refs),
                    freq=q.freq,
                    latest_posted_at=q.latest_posted_at,
                    role_tags=list(q.role_tags),
                    company_tags=list(q.company_tags),
                    topic=q.topic,
                    modality_origin=q.modality_origin,
                    variants=[],
                )
            )
    return clusters
