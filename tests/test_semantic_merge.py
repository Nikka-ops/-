from scripts.corpus.semantic_merge import merge_similar_questions, similarity
from scripts.models import Question


def test_similarity_high_for_paraphrase():
    a = "RAG 召回率低怎么排查"
    b = "RAG 召回率低怎么排查"
    assert similarity(a, b) == 1.0


def test_merge_similar_questions_combines_freq():
    qs = [
        Question("MCP 和 Skill 的区别", ["u1"], company_tags=["字节跳动"]),
        Question("MCP 和 Skill 区别", ["u2"], company_tags=["字节跳动"]),
        Question("Transformer attention 公式", ["u3"]),
    ]
    merged = merge_similar_questions(qs, threshold=0.5)
    assert len(merged) == 2
    mcp = next(q for q in merged if "MCP" in q.text)
    assert mcp.freq == 2
    assert "MCP 和 Skill 区别" in mcp.variants
