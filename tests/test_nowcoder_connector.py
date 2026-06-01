from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.nowcoder import parse_nowcoder_post, NowCoderConnector

FIXTURE = Path(__file__).parent / "fixtures" / "nowcoder_sample.html"
SAMPLE_HTML = FIXTURE.read_text(encoding="utf-8")


def test_parse_extracts_text_and_date():
    post = parse_nowcoder_post(SAMPLE_HTML, "https://nowcoder.com/p/1")
    assert post.source == "nowcoder"
    assert post.url == "https://nowcoder.com/p/1"
    assert post.posted_at == "2025-09-20"
    assert "MCP 和 Skill 的区别" in post.raw_text
    assert "agent 项目架构" in post.raw_text
    assert "字节 AI 应用开发 一面面经" in post.raw_text


def test_connector_search_uses_injected_fetcher():
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"],
        fetcher=lambda url: SAMPLE_HTML,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 1
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("login wall")

    conn = NowCoderConnector(post_urls=["https://nowcoder.com/p/1"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "cookie" in result.message.lower()


def test_parse_missing_date_yields_none():
    html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body text here</p></div>"
    )
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/2")
    assert post.posted_at is None
    assert "body text here" in post.raw_text
    assert post.raw_text.startswith("T")


def test_connector_degrades_when_parsed_content_is_empty():
    drift_html = "<html><body><div class='something-else'>nothing useful</div></body></html>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"], fetcher=lambda url: drift_html
    )
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "selector" in result.message.lower()


def test_parse_handles_only_title_or_only_content():
    title_only_html = "<div class='content-post-title'><h1>仅标题</h1></div>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/3"], fetcher=lambda url: title_only_html
    )
    result = conn.search([])
    assert result.status == "ok"
    assert result.posts[0].raw_text == "仅标题"

    content_only_html = "<div class='nc-slate-editor-content'><p>正文段落</p></div>"
    conn2 = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/4"], fetcher=lambda url: content_only_html
    )
    result2 = conn2.search([])
    assert result2.status == "ok"
    assert "正文段落" in result2.posts[0].raw_text
