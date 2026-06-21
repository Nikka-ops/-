from scripts.corpus.pipeline import build_ranked_questions
from scripts.models import RawPost


def test_pipeline_semantic_merge_reduces_duplicates():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/a",
            post_type="text",
            raw_text="1. MCP 和 Skill 的区别？\n2. MCP 与 Skill 有何区别？",
            posted_at="2026-05-01",
        )
    ]
    ranked = build_ranked_questions(posts, semantic_merge=True, merge_threshold=0.5)
    assert len(ranked) == 1
    assert ranked[0].freq >= 2
