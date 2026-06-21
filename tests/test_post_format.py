from scripts.corpus.post_format import (
    clean_post_text,
    format_body_html,
    resolve_source_url,
)


def test_clean_removes_topic_hashtags():
    raw = "腾讯 ai 应用开发 一面\n#互联网大厂[话题]# #面试[话题]# #agent[话题]#\n1. 项目介绍"
    cleaned = clean_post_text(raw)
    assert "#" not in cleaned
    assert "互联网大厂" not in cleaned or "项目介绍" in cleaned
    assert "1. 项目介绍" in cleaned


def test_format_body_html_paragraphs():
    raw = "标题\n1. 第一点\n2. 第二点\n普通段落"
    html = format_body_html(raw, title="标题")
    assert html.count("<p") >= 3
    assert "bullet" in html


def test_resolve_nowcoder_broken_link():
    url, label = resolve_source_url(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/detail/12345",
        title="后端开发面经",
    )
    assert "search/all" in url
    assert label == "在牛客搜索"


def test_resolve_nowcoder_uuid_link():
    url, label = resolve_source_url(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/f054aef412104109a1dfa85e273e6faf",
        title="后端开发面经",
    )
    assert "feed/main/detail" in url
    assert label == "在牛客查看"
