from scripts.corpus.post_dedupe import dedupe_raw_posts
from scripts.models import RawPost


def test_dedupe_raw_posts_by_url():
    a = RawPost("nowcoder", "https://www.nowcoder.com/feed/main/detail/abc", "text", "same")
    b = RawPost("nowcoder", "https://www.nowcoder.com/feed/main/detail/abc", "text", "dup")
    kept = dedupe_raw_posts([a, b])
    assert len(kept) == 1
