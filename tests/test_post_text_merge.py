from scripts.corpus.post_format import clean_post_text
from scripts.corpus.post_text_merge import merge_article_and_ocr, strip_ocr_page_markers
from scripts.models import RawPost


def test_strip_ocr_page_markers():
    text = "[图片 OCR 第 1 页]\n教育背景\n浙江大学"
    assert strip_ocr_page_markers(text) == "教育背景\n浙江大学"


def test_merge_article_and_ocr():
    merged = merge_article_and_ocr(
        "今年 AI 应用面经分享",
        "[图片 OCR 第 1 页]\n1. RAG 优化\n\n[图片 OCR 第 2 页]\n2. Agent 设计",
    )
    assert "今年 AI 应用面经分享" in merged
    assert "RAG 优化" in merged
    assert "[图片 OCR" not in merged


def test_clean_post_text_strips_ocr_labels():
    assert "[图片 OCR" not in clean_post_text("[图片 OCR 第 1 页]\n正文")


def test_post_article_text_prefers_locator():
    from scripts.corpus.post_text_merge import post_article_text

    post = RawPost(
        source="xiaohongshu",
        url="u",
        post_type="image",
        locator_text="帖子标题\n补充说明",
        raw_text="[图片 OCR 第 1 页]\nOCR内容",
        image_ocr_text="[图片 OCR 第 1 页]\nOCR内容",
    )
    assert post_article_text(post) == "帖子标题\n补充说明"
