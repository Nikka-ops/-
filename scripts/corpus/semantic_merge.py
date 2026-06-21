"""Merge near-duplicate questions by token similarity before freq ranking."""
from __future__ import annotations

from scripts.corpus.dedupe_rank import _max_date, _union, normalize
from scripts.models import Question


def _token_set(text: str) -> set[str]:
    parts = normalize(text).split()
    return {p for p in parts if len(p) >= 2}


def similarity(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _append_variant(into: Question, text: str) -> None:
    t = text.strip()
    if not t or t == into.text:
        return
    if t not in into.variants:
        into.variants.append(t)


def merge_similar_questions(
    questions: list[Question],
    *,
    threshold: float = 0.72,
) -> list[Question]:
    """Greedy cluster merge; keeps the longer text as canonical surface form."""
    clusters: list[Question] = []
    for q in questions:
        best_idx = -1
        best_sim = 0.0
        for i, rep in enumerate(clusters):
            sim = similarity(q.text, rep.text)
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_idx >= 0 and best_sim >= threshold:
            rep = clusters[best_idx]
            _append_variant(rep, q.text)
            rep.freq += q.freq
            rep.latest_posted_at = _max_date(rep.latest_posted_at, q.latest_posted_at)
            _union(rep.source_refs, q.source_refs)
            _union(rep.role_tags, q.role_tags)
            _union(rep.company_tags, q.company_tags)
            # Prefer shorter canonical surface — avoids merged blobs swallowing many questions.
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
