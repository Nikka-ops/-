"""Question bank pipeline: extract → dedupe → agent cluster → rank → answers."""
from __future__ import annotations

from datetime import date

from scripts.corpus.ai_gate import ai_enabled, cluster_questions, enrich_answers
from scripts.corpus.dedupe_rank import dedupe_and_rank
from scripts.corpus.extract_questions import extract_questions
from scripts.corpus.quality import filter_by_companies, filter_questions
from scripts.models import Question, RawPost


def build_ranked_questions(
    posts: list[RawPost],
    *,
    role: str = "数据开发",
    today: date | None = None,
    semantic_merge: bool = True,
    merge_threshold: float = 0.72,
    companies_filter: list[str] | None = None,
    answer_top_n: int = 40,
) -> list[Question]:
    ref = today or date.today()
    ranked = dedupe_and_rank(extract_questions(posts), today=ref)
    # Always run basic quality filter (removes 自我介绍, narrative commentary, non-questions).
    # AI cluster handles semantic merging and topic assignment on top of this.
    ranked = filter_questions(ranked)
    if semantic_merge:
        ranked = cluster_questions(ranked, offline_threshold=merge_threshold, today=ref)
    if companies_filter:
        ranked = filter_by_companies(ranked, companies_filter)
    return enrich_answers(ranked, role, top_n=answer_top_n)
