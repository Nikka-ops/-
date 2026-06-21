from scripts.agent_handoff import build_agent_context, render_agent_handoff_md, write_agent_handoff
from scripts.models import Question, RawPost


def test_build_agent_context_flags_vision_resume():
    ctx = build_agent_context(
        role="AI 应用开发",
        companies=["字节跳动"],
        posts=[],
        ranked=[Question("RAG 怎么优化?", ["u1"], freq=2, topic="RAG")],
        bank={"role": "AI 应用开发", "question_count": 1, "questions": []},
        paths={"question_bank": "/tmp/bank.json"},
        resume=None,
        resume_text="",
        ingest_mode="ingest",
        sources={},
    )
    assert ctx["prep_mode"] == "agent"
    assert "agent_steps" in ctx
    assert len(ctx["question_candidates"]) == 1


def test_write_agent_handoff_files(tmp_path):
    ctx = {
        "generated_at": "2026-06-18",
        "role": "AI 应用开发",
        "resume": {"text": "Python RAG", "needs_vision": False, "asset_path": ""},
        "posts_needing_vision": [],
        "paths": {},
        "taxonomy": [],
        "question_candidates": [],
        "agent_steps": ["7. 项目锚定"],
        "constraints": ["禁止编造"],
        "outputs_expected": {"prep_package": "corpus_cache/prep_package.md"},
    }
    md, js = write_agent_handoff(tmp_path, "slug1", ctx)
    assert md.is_file()
    assert js.is_file()
    text = md.read_text(encoding="utf-8")
    assert "Agent 交接包" in text
    assert render_agent_handoff_md(ctx).startswith("# Agent")
