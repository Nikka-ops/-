from scripts.discover.nowcoder_urls import (
    discover_nowcoder_urls,
    extract_nowcoder_urls_from_html,
    normalize_nowcoder_discuss_url,
)

SAMPLE_HTML = """
<html><body>
<a href="https://www.nowcoder.com/discuss/882634966025175040">面经1</a>
<a href="//www.nowcoder.com/discuss/881209147377664000">面经2</a>
<a href="https://www.nowcoder.com/discuss/list">skip list</a>
</body></html>
"""


def test_normalize_nowcoder_discuss_url():
    assert (
        normalize_nowcoder_discuss_url("https://www.nowcoder.com/discuss/123")
        == "https://www.nowcoder.com/discuss/123"
    )
    assert normalize_nowcoder_discuss_url("https://www.nowcoder.com/discuss/list") is None


def test_extract_nowcoder_urls_from_html():
    urls = extract_nowcoder_urls_from_html(SAMPLE_HTML)
    assert urls == [
        "https://www.nowcoder.com/discuss/882634966025175040",
        "https://www.nowcoder.com/discuss/881209147377664000",
    ]


def test_discover_nowcoder_urls_dedupes_and_limits():
    def fake_fetcher(query: str) -> str:
        return SAMPLE_HTML

    urls, meta = discover_nowcoder_urls(
        ["AI 应用开发 面经", "Agent 面经"],
        max_per_query=1,
        search_fetcher=fake_fetcher,
        request_delay=0,
    )
    assert len(urls) == 2
    assert meta["count"] == 2
