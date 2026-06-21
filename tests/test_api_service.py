from pathlib import Path
from urllib.parse import quote

from scripts.api.server import handle_request
from scripts.models import RawPost
from scripts.corpus.store import save_raw_posts
from scripts.service import RunConfig, run_pipeline


def test_handle_health():
    status, payload = handle_request("GET", "/health")
    assert status == 200
    assert payload["status"] == "ok"


def test_handle_bank_missing_role():
    status, payload = handle_request("POST", "/api/bank", {})
    assert status == 400


def test_run_pipeline_with_raw_posts(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text="1. RAG 召回怎么优化？",
            posted_at="2026-05-01",
            company="字节跳动",
            role="AI 应用开发",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    cache_dir = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)

    config = RunConfig(
        role="AI 应用开发",
        raw_posts=str(raw),
        cache_dir=str(cache_dir),
        refresh=True,
    )
    result = run_pipeline(config)
    assert result.ranked_count >= 1
    assert Path(result.paths["question_bank"]).is_file()


def test_handle_bank_no_handoff(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text="1. RAG 召回怎么优化？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    monkeypatch.chdir(tmp_path)

    status, payload = handle_request(
        "POST",
        "/api/bank",
        {
            "role": "AI 应用开发",
            "raw_posts": str(raw),
            "cache_dir": str(tmp_path / "banks"),
            "refresh": True,
        },
    )
    assert status == 200
    assert payload.get("bank")
    assert payload.get("posts") is not None
    assert payload.get("companies") is not None
    assert payload["paths"]["question_bank"]


def test_list_and_get_bank_api(tmp_path: Path, monkeypatch):
    import scripts.api.server as srv

    banks = tmp_path / "banks"
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/3",
            post_type="text",
            raw_text="1. Agent 记忆模块？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(srv, "banks_dir", lambda: banks)

    build_status, build_payload = handle_request(
        "POST",
        "/api/bank",
        {
            "role": "Agent开发",
            "raw_posts": str(raw),
            "cache_dir": str(banks),
            "refresh": True,
        },
    )
    assert build_status == 200
    slug = build_payload["slug"]
    assert build_payload.get("posts") is not None

    list_status, list_payload = handle_request("GET", "/api/banks")
    assert list_status == 200
    assert any(b["slug"] == slug for b in list_payload["banks"])

    get_status, get_payload = handle_request("GET", f"/api/banks/{slug}")
    assert get_status == 200
    assert get_payload["bank"]["role"] == "Agent开发"
    assert len(get_payload["posts"]) >= 1
    assert len(get_payload["companies"]) >= 1

    encoded = "AI_%E5%BA%94%E7%94%A8%E5%BC%80%E5%8F%91_c6870bcf7a"
    enc_status, enc_payload = handle_request("GET", f"/api/banks/{quote(slug, safe='')}")
    assert enc_status == 200
    assert enc_payload["bank"]["role"] == "Agent开发"

    missing_status, _ = handle_request("GET", "/api/banks/not-exists")
    assert missing_status == 404


def test_handle_predict_api(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/2",
            post_type="text",
            raw_text="1. 介绍你的 RAG 项目？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    monkeypatch.chdir(tmp_path)

    status, payload = handle_request(
        "POST",
        "/api/predict",
        {
            "role": "AI 应用开发",
            "resume_text": "项目: RAG LangChain Python",
            "raw_posts": str(raw),
            "cache_dir": str(tmp_path / "banks"),
            "refresh": True,
        },
    )
    assert status == 200
    assert payload.get("agent_handoff")
    assert payload["prep_mode"] == "agent"
