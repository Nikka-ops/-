"""Shared question-bank build pipeline."""
from __future__ import annotations

from datetime import date

from scripts.corpus.dedupe_rank import dedupe_and_rank
from scripts.corpus.extract_questions import extract_questions
from scripts.corpus.quality import filter_by_companies, filter_questions
from scripts.corpus.semantic_merge import merge_similar_questions
from scripts.models import Question, RawPost


def build_ranked_questions(
    posts: list[RawPost],
    *,
    today: date | None = None,
    semantic_merge: bool = True,
    merge_threshold: float = 0.72,
    companies_filter: list[str] | None = None,
) -> list[Question]:
    raw = extract_questions(posts)
    if semantic_merge:
        raw = merge_similar_questions(raw, threshold=merge_threshold)
    ranked = dedupe_and_rank(raw, today=today or date.today())
    ranked = filter_questions(ranked)
    if companies_filter:
        ranked = filter_by_companies(ranked, companies_filter)
    return ranked
