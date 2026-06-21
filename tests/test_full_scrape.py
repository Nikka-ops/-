"""Tests for full scrape tooling."""
from scripts.tools.full_scrape import _stage_counts
from scripts.models import RawPost


def test_stage_counts_role_and_recency():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/feed/main/detail/a",
            post_type="text",
            raw_text="字节跳动 AI 应用开发 面经 RAG Agent",
            posted_at="2026-06-01",
        ),
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/feed/main/detail/b",
            post_type="text",
            raw_text="纯后端 Java 八股",
            posted_at="2026-06-01",
        ),
    ]
    stages = _stage_counts(posts, "AI 应用开发", 90)
    assert stages["raw"] == 2
    assert stages["after_role_filter"] >= 1
    assert stages["after_recency"] >= 1
