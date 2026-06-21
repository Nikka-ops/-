from scripts.corpus.group import group_posts_by_taxonomy, taxonomy_summary
from scripts.models import RawPost


def test_group_posts_by_taxonomy():
    posts = [
        RawPost("nowcoder", "u1", "text", "q1", company="字节跳动", role="AI 应用开发"),
        RawPost("xiaohongshu", "u2", "image", "q2", company="字节跳动", role="AI 应用开发"),
        RawPost("nowcoder", "u3", "text", "q3", company="腾讯", role="产品经理"),
        RawPost("nowcoder", "u4", "text", "q4"),
    ]
    grouped = group_posts_by_taxonomy(posts)
    assert len(grouped["字节跳动"]["AI 应用开发"]) == 2
    assert len(grouped["腾讯"]["产品经理"]) == 1
    assert len(grouped["未标注"]["未标注"]) == 1


def test_taxonomy_summary_counts_sources():
    posts = [
        RawPost("nowcoder", "u1", "text", "q1", company="字节跳动", role="AI 应用开发"),
        RawPost("xiaohongshu", "u2", "image", "q2", company="字节跳动", role="AI 应用开发"),
    ]
    rows = taxonomy_summary(posts)
    assert rows[0]["company"] == "字节跳动"
    assert rows[0]["role"] == "AI 应用开发"
    assert rows[0]["count"] == 2
    assert set(rows[0]["sources"]) == {"nowcoder", "xiaohongshu"}
