from scripts.models import Question
from scripts.corpus.dedupe_rank import normalize, dedupe_and_rank


def test_normalize_strips_case_punctuation_whitespace():
    assert normalize("  What is  MCP??  ") == normalize("what is mcp")


def test_dedupe_merges_and_sums_freq():
    qs = [
        Question("What is MCP?", ["u1"], role_tags=["agent"]),
        Question("what is  mcp", ["u2"], role_tags=["llm"]),
        Question("What is RAG?", ["u3"]),
    ]
    out = dedupe_and_rank(qs)
    assert len(out) == 2
    top = out[0]
    assert top.freq == 2
    assert top.source_refs == ["u1", "u2"]
    assert top.role_tags == ["agent", "llm"]


def test_rank_sorts_by_freq_desc():
    qs = [
        Question("rare", ["a"]),
        Question("common", ["b"]),
        Question("common", ["c"]),
    ]
    out = dedupe_and_rank(qs)
    assert out[0].text == "common"
    assert out[0].freq == 2
    assert out[1].text == "rare"
