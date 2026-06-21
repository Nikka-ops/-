import base64
from pathlib import Path

from scripts.api.server import STATIC_DIR, _local_report_status, _resolve_static, handle_request
from scripts.api.uploads import save_resume_base64


def test_static_index_resolves():
    path = _resolve_static("/")
    assert path == STATIC_DIR / "index.html"
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "feed-grid" in html
    assert "searchQ" in html
    assert "roleChipRow" in html
    assert "viewJobs" in html
    assert "submitJobs" in html


def test_static_style_resolves():
    path = _resolve_static("/static/style.css")
    assert path is not None
    assert path.name == "style.css"


def test_api_status_reports_local_report(tmp_path, monkeypatch):
    report = tmp_path / "scrape_smoke_report.json"
    report.write_text('{"posts": [{"url": "u1"}, {"url": "u2"}]}', encoding="utf-8")
    import scripts.api.server as srv

    monkeypatch.setattr(srv, "_local_corpus_path", lambda: report)
    status, payload = handle_request("GET", "/api/status")
    assert status == 200
    assert payload["local_post_count"] == 2


def test_api_status_includes_sample_posts():
    status, payload = handle_request("GET", "/api/status")
    assert status == 200
    assert payload.get("sample_posts")


def test_api_jobs_list():
    status, payload = handle_request("GET", "/api/jobs")
    assert status == 200
    assert "snapshots" in payload
    assert "cache_dir" in payload
    status, payload = handle_request("GET", "/api/roles")
    assert status == 200
    assert payload["default_role_id"] == "ai_app"
    labels = [r["label"] for r in payload["roles"]]
    assert "大模型" in labels
    assert "数据开发" in labels


def test_save_resume_base64_roundtrip(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    content = "Skill driven agent project Python RAG".encode("utf-8")
    encoded = base64.b64encode(content).decode("ascii")
    saved = Path(save_resume_base64("resume.txt", encoded))
    assert saved.is_file()
    assert saved.read_bytes() == content


def test_predict_with_resume_base64(tmp_path, monkeypatch):
    from scripts.models import RawPost
    from scripts.corpus.store import save_raw_posts

    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/9",
            post_type="text",
            raw_text="1. 介绍 RAG 项目架构？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    monkeypatch.chdir(tmp_path)

    encoded = base64.b64encode("项目: RAG LangChain".encode("utf-8")).decode("ascii")
    status, payload = handle_request(
        "POST",
        "/api/predict",
        {
            "role": "AI 应用开发",
            "resume_base64": encoded,
            "resume_filename": "resume.txt",
            "raw_posts": str(raw),
            "refresh": True,
            "cache_dir": str(tmp_path / "banks"),
        },
    )
    assert status == 200
    assert payload.get("agent_handoff")
