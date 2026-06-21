from scripts.corpus.posts_view import company_options, post_title, serialize_posts
from scripts.models import RawPost


def test_post_title_first_line():
    post = RawPost(
        source="nowcoder",
        url="u",
        post_type="text",
        raw_text="字节 AI 应用开发一面面经\n\n1. RAG 怎么优化？",
        company="字节跳动",
    )
    assert "面经" in post_title(post)


def test_company_options_sorted():
    posts = [
        RawPost("n", "u1", "text", "a", company="字节跳动"),
        RawPost("n", "u2", "text", "b", company="字节跳动"),
        RawPost("n", "u3", "text", "c", company="美团"),
        RawPost("n", "u4", "text", "d"),
    ]
    opts = company_options(posts)
    assert opts[0]["name"] == "字节跳动"
    assert opts[0]["count"] == 2
    assert any(o["name"] == "未标注" for o in opts)


def test_serialize_posts_includes_preview():
    posts = [
        RawPost(
            source="xiaohongshu",
            url="https://xhs/1",
            post_type="text",
            raw_text="标题面经\n正文很长" * 5,
            posted_at="2026-05-01",
            company="腾讯",
            role="AI 应用开发",
        )
    ]
    rows = serialize_posts(posts)
    assert len(rows) == 1
    assert rows[0]["title"]
    assert rows[0]["preview"]
    assert rows[0]["company_label"] == "腾讯"
