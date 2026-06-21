from datetime import date

from scripts.corpus.dedupe_rank import dedupe_and_rank
from scripts.corpus.export_bank import build_question_bank, render_frequency_report
from scripts.corpus.personalize import (
    build_followup_chains,
    predict_questions,
    score_resume_match,
)
from scripts.models import Question


def _sample_ranked() -> list[Question]:
    qs = [
        Question(
            "RAG 召回率低怎么排查？",
            ["u1"],
            freq=1,
            company_tags=["字节跳动"],
            role_tags=["AI 应用开发"],
            topic="RAG",
            latest_posted_at="2026-04-01",
        ),
        Question(
            "Agent 短期记忆和长期记忆怎么设计？",
            ["u2"],
            freq=1,
            topic="Agent",
            latest_posted_at="2026-03-01",
        ),
    ]
    return dedupe_and_rank(qs, today=date(2026, 6, 18))


def test_build_question_bank_structure():
    ranked = _sample_ranked()
    bank = build_question_bank(
        role="AI 应用开发",
        companies=["字节跳动"],
        ranked=ranked,
        post_count=5,
        sources_meta={"nowcoder": {"count": 5}},
    )
    assert bank["role"] == "AI 应用开发"
    assert bank["question_count"] == 2
    assert bank["cluster_count"] == 2
    assert bank["clusters"][0]["rank"] == 1
    assert bank["recency_window_days"] == 90
    assert bank["questions"][0]["confidence"] in {"高频", "中频", "低频"}
    assert bank["taxonomy"]


def test_render_frequency_report_contains_top():
    ranked = _sample_ranked()
    bank = build_question_bank(
        role="AI 应用开发",
        companies=[],
        ranked=ranked,
        post_count=2,
        sources_meta={},
    )
    md = render_frequency_report(bank, top_n=5)
    assert "高频题簇 Top" in md
    assert "RAG" in md


def test_resume_match_prefers_overlap():
    q = Question("Python RAG 项目里 embedding 召回怎么优化？", topic="RAG")
    resume = "项目: RAG 知识库 Python embedding 检索优化"
    assert score_resume_match(q, resume, role="AI 应用开发") >= 0.2


def test_predict_and_followup_chains():
    ranked = _sample_ranked()
    resume = "技能: Python LangChain RAG Pinecone"
    predicted = predict_questions(ranked, resume, role="AI 应用开发", top_n=5)
    assert predicted
    assert "combined_score" in predicted[0]
    chains = build_followup_chains(predicted, resume, max_chains=2)
    assert len(chains) == 2
    assert chains[0].seed_question
