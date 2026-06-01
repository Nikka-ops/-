from datetime import date

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


def test_merge_keeps_most_recent_date():
    qs = [
        Question("What is MCP?", ["u1"], latest_posted_at="2024-01-01"),
        Question("what is  mcp", ["u2"], latest_posted_at="2025-06-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert len(out) == 1
    assert out[0].latest_posted_at == "2025-06-01"
    assert out[0].freq == 2


def test_recency_weight_can_outrank_lower_freq_when_close():
    # old item freq=2 → score 2*0.3=0.6 ; fresh item freq=1 → score 1*1.0=1.0
    qs = [
        Question("old hot", ["a"], freq=2, latest_posted_at="2023-01-01"),
        Question("fresh", ["b"], freq=1, latest_posted_at="2026-04-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert out[0].text == "fresh"


def test_undated_ranks_below_known_stale():
    # New policy: undated (0.2) ranks BELOW known-stale (0.3).
    # freq all 1: fresh(1.0) > stale(0.3) > undated(0.2)
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("undated", ["b"], latest_posted_at=None),
        Question("fresh", ["c"], latest_posted_at="2026-05-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["fresh", "stale", "undated"]


def test_malformed_date_treated_as_undated():
    # Malformed posted_at should weight the same as None (0.2), i.e. rank below known-stale.
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("garbled", ["b"], latest_posted_at="not-a-date"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["stale", "garbled"]
