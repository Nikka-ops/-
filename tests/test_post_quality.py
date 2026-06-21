from scripts.corpus.post_quality import is_interview_experience_post, filter_interview_experience_posts
from scripts.models import RawPost


def test_rejects_career_direction_chatter():
    post = RawPost(
        source="xiaohongshu",
        url="https://xhs.com/1",
        post_type="text",
        raw_text="今年就业方向 Java+Agent 还是 RAG 啊 感觉没什么面试啊 暑期应该是 gg 了 秋招大家觉得应该选什么啊",
        locator_text="今年就业方向 Java+Agent 还是 RAG 啊",
    )
    assert not is_interview_experience_post(post)


def test_accepts_real_interview_recap():
    post = RawPost(
        source="nowcoder",
        url="https://nowcoder.com/1",
        post_type="text",
        raw_text="字节 AI 应用开发一面面经\n1. 介绍项目\n2. RAG 链路怎么设计？",
    )
    assert is_interview_experience_post(post)


def test_rejects_ad_without_interview_signal():
    post = RawPost(
        source="nowcoder",
        url="https://nowcoder.com/2",
        post_type="text",
        raw_text="急聘 Java 开发，内推码私信我，岗位要求三年经验，月薪 25k",
    )
    assert not is_interview_experience_post(post)


def test_filter_splits_kept_and_dropped():
    good = RawPost(
        source="nowcoder",
        url="https://nowcoder.com/3",
        post_type="text",
        raw_text="美团 Agent 二面凉经\n面试官问了 MCP 和工具调用",
    )
    bad = RawPost(
        source="xiaohongshu",
        url="https://xhs.com/2",
        post_type="text",
        raw_text="点赞收藏关注，就业方向选 Java 还是 Go",
    )
    kept, dropped = filter_interview_experience_posts([good, bad])
    assert len(kept) == 1
    assert kept[0].url.endswith("/3")
    assert len(dropped) == 1
