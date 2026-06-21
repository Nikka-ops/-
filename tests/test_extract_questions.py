from scripts.corpus.extract_questions import extract_questions, extract_questions_from_post, infer_topic
from scripts.models import RawPost


def test_infer_topic_rag():
    assert infer_topic("RAG 召回率低怎么排查？") == "RAG"


def test_extract_numbered_questions_from_post():
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/discuss/1",
        post_type="text",
        raw_text=(
            "一面 50min\n"
            "1. embedding 向量检索的原理是什么？\n"
            "2. function calling 如何解析用户意图？\n"
            "感受：很难"
        ),
        posted_at="2026-03-01",
        company="字节跳动",
        role="AI 应用开发",
    )
    qs = extract_questions_from_post(post)
    texts = [q.text for q in qs]
    assert any("embedding" in t for t in texts)
    assert any("function calling" in t for t in texts)
    assert all(q.company_tags == ["字节跳动"] for q in qs)


def test_extract_skips_noise_lines():
    post = RawPost(
        source="xiaohongshu",
        url="https://www.xiaohongshu.com/explore/n1",
        post_type="text",
        raw_text="点赞收藏关注\n#面经分享#",
    )
    assert extract_questions_from_post(post) == []


def test_extract_inline_numbered_on_same_line():
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/discuss/x",
        post_type="text",
        raw_text=(
            "你们的测试数据里会不会涉及敏感信息？有没有风险？ "
            "18. 这个分析平台的技术难点在哪里？ "
            "19. 为什么最终选择了OpenAI的模型？"
        ),
        company="字节跳动",
    )
    qs = extract_questions_from_post(post)
    texts = [q.text for q in qs]
    assert len(texts) >= 2
    assert any("敏感信息" in t for t in texts)
    assert any("OpenAI" in t or "分析平台" in t for t in texts)


def test_extract_from_image_ocr_text():
    post = RawPost(
        source="xiaohongshu",
        url="https://www.xiaohongshu.com/explore/n2",
        post_type="image",
        raw_text="图片面经",
        content_text="图片面经",
        image_ocr_text="1. RAG 检索怎么做？\n2. Agent 工具调用怎么设计？",
        extraction_quality="ocr_ok",
        company="美团",
        role="AI 应用开发",
    )
    qs = extract_questions_from_post(post)
    assert len(qs) == 2
    assert qs[0].modality_origin == "ocr"


def test_extract_questions_across_posts():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/a",
            post_type="text",
            raw_text="问了 MCP 和 Skill 的区别？",
            company="字节跳动",
        ),
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/b",
            post_type="text",
            raw_text="问了 mcp 和 skill 的区别？",
            company="字节跳动",
        ),
    ]
    qs = extract_questions(posts)
    assert len(qs) == 2
