from scripts.corpus.post_format import format_body_html, split_body_lines, strip_duplicate_title
from scripts.discover.nowcoder_detail import fetch_nowcoder_moment_full, needs_full_fetch


def test_split_inline_numbered_lines():
    raw = "前言 1.第一点 2.第二点 3.第三点"
    lines = split_body_lines(raw)
    assert any("第一点" in ln for ln in lines)
    assert any(ln.startswith("2") for ln in lines)


def test_strip_duplicate_title():
    body = strip_duplicate_title("字节测开面经", "字节测开面经\n1.问题一")
    assert body.startswith("1.")


def test_format_body_skips_duplicate_title():
    html = format_body_html("字节测开面经\n1.问题一\n2.问题二", title="字节测开面经")
    assert "字节测开面经" not in html or html.count("字节") == 0
    assert "问题一" in html


def test_needs_full_fetch_on_ellipsis():
    assert needs_full_fetch("1. aaa…2. bbb")
    assert not needs_full_fetch("1. aaa\n2. bbb\n3. ccc")


def test_fetch_nowcoder_moment_full_live():
    text = fetch_nowcoder_moment_full("f65b692f76244441a53cecb6f435fcc6", use_cache=True)
    assert "RAG" in text or "幻觉" in text
    assert "…" not in text or text.count("\n") >= 5
