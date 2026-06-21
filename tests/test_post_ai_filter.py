import json

from scripts.corpus.post_ai_filter import (
    filter_interview_experience_posts_hybrid,
    _parse_ai_json,
)
from scripts.corpus.post_quality import rule_post_verdict
from scripts.models import RawPost


def test_parse_ai_json():
    keep, reason = _parse_ai_json('{"keep": false, "reason": "就业闲聊"}')
    assert keep is False
    assert "就业" in reason


def test_rule_verdict_career_chat_is_drop():
    post = RawPost(
        source="xiaohongshu",
        url="https://xhs.com/chat",
        post_type="text",
        raw_text="今年就业方向 Java+Agent 还是 RAG 啊 感觉没什么面试",
    )
    assert rule_post_verdict(post) == "drop"


def test_rule_verdict_interview_is_keep():
    post = RawPost(
        source="nowcoder",
        url="https://nowcoder.com/1",
        post_type="text",
        raw_text="字节 AI 应用一面面经\n1. 项目\n2. RAG？",
    )
    assert rule_post_verdict(post) == "keep"


def test_hybrid_ai_drops_review_when_model_says_no(monkeypatch, tmp_path):
    from scripts.config import cache_dir

    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")

    borderline = RawPost(
        source="xiaohongshu",
        url="https://xhs.com/border",
        post_type="image",
        raw_text="分享下求职体会",
        asset_paths=["https://img.example/a.jpg"],
    )
    good = RawPost(
        source="nowcoder",
        url="https://nowcoder.com/ok",
        post_type="text",
        raw_text="美团二面面经\n1. Agent 架构",
    )

    def fake_classify(snippet, timeout=25.0):
        if "求职体会" in snippet:
            return False, "非面经"
        return True, "面经"

    monkeypatch.setattr(
        "scripts.corpus.post_ai_filter.deepseek_classify_post",
        fake_classify,
    )

    kept, dropped, meta = filter_interview_experience_posts_hybrid(
        [borderline, good], request_delay=0
    )
    assert len(kept) == 1
    assert kept[0].url.endswith("/ok")
    assert len(dropped) == 1
    assert meta["ai_review"] == 1
    assert meta["ai_drop"] == 1

    cache_file = cache_dir() / "daily" / "post_ai_filter_cache.json"
    assert cache_file.is_file()
    cache = json.loads(cache_file.read_text())
    assert cache["https://xhs.com/border"]["keep"] is False
