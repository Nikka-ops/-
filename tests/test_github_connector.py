from scripts.connectors.base import SearchResult
from scripts.connectors.github import extract_posts_from_markdown, GithubConnector


SAMPLE_MD = """# Agent 面经
## 一面
- 说明 MCP 和 Skill 的区别
- 什么是 RAG？
随便一句不是题目的话。
### 项目相关
1. 介绍一下你的 agent 项目架构
"""


def test_extract_picks_question_like_lines():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    texts = [p.raw_text for p in posts]
    assert "说明 MCP 和 Skill 的区别" in texts
    assert "什么是 RAG？" in texts
    assert "介绍一下你的 agent 项目架构" in texts
    assert "随便一句不是题目的话。" not in texts


def test_extract_sets_source_and_url():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    assert all(p.source == "github" for p in posts)
    assert all(p.url == "https://example.com/repo" for p in posts)
    assert all(p.post_type == "text" for p in posts)


def test_connector_search_uses_injected_fetcher():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert any("RAG" in p.raw_text for p in result.posts)


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("network down")

    conn = GithubConnector(repo_raw_urls=["https://example.com/repo"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []


def test_extract_with_hints_keeps_only_matching():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["RAG"],
    )
    texts = [p.raw_text for p in posts]
    assert "什么是 RAG？" in texts
    assert "说明 MCP 和 Skill 的区别" not in texts
    assert "介绍一下你的 agent 项目架构" not in texts


def test_extract_with_hints_case_insensitive():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["mcp"],  # lowercase, candidate has uppercase MCP
    )
    texts = [p.raw_text for p in posts]
    assert any("MCP" in t for t in texts)
    assert all("RAG" not in t for t in texts)


def test_extract_with_empty_hints_does_not_filter():
    posts_none = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=None)
    posts_empty = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=[])
    assert {p.raw_text for p in posts_none} == {p.raw_text for p in posts_empty}
    assert len(posts_empty) >= 3  # all question-like lines


def test_connector_passes_hints_through():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
        relevance_hints=["agent"],
    )
    result = conn.search([])
    assert result.status == "ok"
    texts = [p.raw_text for p in result.posts]
    assert any("agent" in t.lower() for t in texts)
    assert all("RAG" not in t for t in texts)


def test_extract_with_empty_string_hint_does_not_match_all():
    # Defensive: a stray empty-string hint must not turn into "match everything"
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["", "RAG"],
    )
    texts = [p.raw_text for p in posts]
    assert "什么是 RAG？" in texts
    assert "说明 MCP 和 Skill 的区别" not in texts
