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
