from scripts.corpus.role_match import (
    filter_posts_for_bank,
    infer_preset_from_text,
    refine_extracted_role,
    score_post_for_bank,
)
from scripts.models import RawPost


def test_infer_qa_over_llm_for_cekai_title():
    preset = infer_preset_from_text("字节春招大模型测开一面面经")
    assert preset is not None
    assert preset.id == "qa"


def test_refine_extracted_role_maps_to_preset():
    role = refine_extracted_role(title="美团 Agent 方向面经整理")
    assert role is not None
    assert role in {"AI 应用开发", "AI/Agent 应用开发"}


def test_infer_preset_from_post_prefers_title_line():
    from scripts.corpus.role_match import infer_preset_from_post
    from scripts.models import RawPost

    post = RawPost(
        source="nowcoder",
        url="https://example.com/1",
        post_type="text",
        raw_text="领境科技前端开发面经\n后面是正文…",
    )
    assert infer_preset_from_post(post).id == "frontend"


def test_filter_drops_mismatched_post():
    target = "大模型"
    bad = RawPost(
        source="nowcoder",
        url="https://example.com/1",
        post_type="text",
        raw_text="字节测开一面：自动化测试框架怎么设计",
        role="测试开发",
    )
    good = RawPost(
        source="nowcoder",
        url="https://example.com/2",
        post_type="text",
        raw_text="大模型 RLHF 训练流程与 SFT 数据构造",
        role="大模型",
    )
    kept, dropped = filter_posts_for_bank([bad, good], target)
    assert len(kept) == 1
    assert kept[0].url.endswith("/2")
    assert len(dropped) == 1


def test_score_related_ai_roles_not_hard_mismatch():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/3",
        post_type="text",
        raw_text="RAG 检索增强与 Agent 工具调用面经",
        role="AI 应用开发",
    )
    score, mismatch = score_post_for_bank(post, "Agent开发")
    assert score >= 0.4
    assert mismatch is False
