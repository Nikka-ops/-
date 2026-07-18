"""Consolidated: test_api_service.py, test_web_ui.py, test_run.py, test_agent_handoff.py, test_config.py, test_resume_extract.py, test_ocr_extract.py"""


# --- test_api_service.py ---

from argparse import Namespace
import base64
from pathlib import Path
from urllib.parse import quote

from scripts.api.server import handle_request
from scripts.api.uploads import UploadValidationError, save_resume_base64
from scripts.models import RawPost
from scripts.corpus.store import save_raw_posts
from scripts.run import _config_from_args, main
from scripts.service import RunConfig, run_pipeline


def test_handle_health():
    status, payload = handle_request("GET", "/health")
    assert status == 200
    assert payload["status"] == "ok"


def test_handle_bank_missing_role():
    status, payload = handle_request("POST", "/api/bank", {})
    assert status == 400


def test_run_pipeline_with_raw_posts(tmp_path: Path, monkeypatch):
    # Force offline filtering: deterministic, no network in CI or locally.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text="AI应用开发面经：一面被拷打。1. RAG 召回怎么优化？",
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
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text="AI应用开发面经：一面被拷打。1. RAG 召回怎么优化？",
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
            raw_text="面经复盘：一面被拷打。1. Agent 记忆模块？",
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
            raw_text="面经复盘：一面被拷打。1. 介绍你的 RAG 项目？",
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

# --- test_web_ui.py ---

from scripts.api.server import STATIC_DIR, _local_report_status, _resolve_static, handle_request


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
    assert payload["app_mode"] in {"basic", "enhanced"}
    assert payload["app_mode_label"]
    assert payload["demo_role_id"] == "ai_app"


def test_api_settings_get(tmp_path, monkeypatch):
    import scripts.config as cfg
    import scripts.api.server as srv

    env_path = tmp_path / ".env"
    monkeypatch.setattr(cfg, "project_env_path", lambda: env_path)
    monkeypatch.setattr(srv, "project_env_path", lambda: env_path)
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    status, payload = handle_request("GET", "/api/settings")
    assert status == 200
    assert payload["deepseek"]["configured"] is False
    assert payload["deepseek"]["api_base"] == "https://api.deepseek.com"
    assert payload["sources"]["xiaohongshu"]["configured"] is False
    assert payload["sources"]["xiaohongshu"]["driver"] == "playwright"
    assert payload["sources"]["boss"]["configured"] is False
    assert payload["env_path"] == str(env_path)


def test_api_settings_save(tmp_path, monkeypatch):
    import scripts.config as cfg
    import scripts.api.server as srv

    env_path = tmp_path / ".env"
    monkeypatch.setattr(cfg, "project_env_path", lambda: env_path)
    monkeypatch.setattr(srv, "project_env_path", lambda: env_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    status, payload = handle_request(
        "POST",
        "/api/settings/save",
        {
            "deepseek_api_key": "sk-test-123",
            "deepseek_api_base": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
        },
    )
    assert status == 200
    assert payload["deepseek"]["configured"] is True
    text = env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-test-123" in text

    status_sources, payload_sources = handle_request(
        "POST",
        "/api/settings/save",
        {
            "xhs_driver": "spider_xhs",
            "xhs_cookies": "web_session=test_cookie; a1=abc",
            "boss_cookie": "wt2=boss_cookie_value_123456789",
        },
    )
    assert status_sources == 200
    updated_text = env_path.read_text(encoding="utf-8")
    assert "XHS_DRIVER=spider_xhs" in updated_text
    assert "XHS_COOKIES=web_session=test_cookie; a1=abc" in updated_text
    assert "BOSS_ZHIPIN_COOKIE=wt2=boss_cookie_value_123456789" in updated_text

    status2, payload2 = handle_request(
        "POST",
        "/api/settings/save",
        {
            "clear_deepseek_api_key": True,
            "clear_xhs_cookies": True,
            "clear_boss_cookie": True,
            "deepseek_api_base": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
        },
    )
    assert status2 == 200
    assert payload2["deepseek"]["configured"] is False
    final_text = env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" not in final_text
    assert "XHS_COOKIES=" not in final_text
    assert "BOSS_ZHIPIN_COOKIE=" not in final_text


def test_xhs_run_safe_prefers_playwright(monkeypatch):
    import scripts.scrape.xhs_export as xhs

    called: list[str] = []

    monkeypatch.setattr(xhs, "_driver_order", lambda: ["playwright", "spider_xhs"])
    monkeypatch.setattr(xhs, "_playwright_ready", lambda: True)
    monkeypatch.setenv("XHS_COOKIES", "web_session=test_cookie; a1=abc")

    def fake_run(driver_name, keywords, **kwargs):
        called.append(driver_name)
        return {"ok": True, "driver": driver_name, "keywords": keywords}

    monkeypatch.setattr(xhs, "_run_driver_scrape", fake_run)
    result = xhs.run_safe_xhs_scrape(["数据开发 面经"])
    assert result["driver"] == "playwright"
    assert called == ["playwright"]


def test_xhs_run_safe_falls_back_to_spider(monkeypatch):
    import scripts.scrape.xhs_export as xhs

    called: list[str] = []

    monkeypatch.setattr(xhs, "_driver_order", lambda: ["playwright", "spider_xhs"])
    monkeypatch.setattr(xhs, "_playwright_ready", lambda: True)
    monkeypatch.setenv("XHS_COOKIES", "web_session=test_cookie; a1=abc")

    def fake_run(driver_name, keywords, **kwargs):
        called.append(driver_name)
        if driver_name == "playwright":
            raise RuntimeError("cdp unavailable")
        return {"ok": True, "driver": driver_name, "keywords": keywords}

    monkeypatch.setattr(xhs, "_run_driver_scrape", fake_run)
    result = xhs.run_safe_xhs_scrape(["数据开发 面经"])
    assert result["driver"] == "spider_xhs"
    assert called == ["playwright", "spider_xhs"]


def test_api_jobs_list():
    status, payload = handle_request("GET", "/api/jobs")
    assert status == 200
    assert "snapshots" in payload
    assert "cache_dir" in payload
    status, payload = handle_request("GET", "/api/roles")
    assert status == 200
    assert payload["default_role_id"] == "data"
    assert payload["focus_role_ids"] == ["data", "ai_app"]
    assert len(payload["roles"]) == 2
    labels = [r["label"] for r in payload["roles"]]
    assert "数据开发" in labels
    assert "Agent 开发" in labels


def test_save_resume_base64_roundtrip(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    content = "Skill driven agent project Python RAG".encode("utf-8")
    encoded = base64.b64encode(content).decode("ascii")
    saved = Path(save_resume_base64("resume.txt", encoded))
    assert saved.is_file()
    assert saved.read_bytes() == content


def test_save_resume_base64_rejects_oversize(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    encoded = base64.b64encode(b"a" * (up._MAX_UPLOAD_BYTES + 1)).decode("ascii")
    try:
        save_resume_base64("resume.txt", encoded)
    except UploadValidationError as exc:
        assert "file too large" in str(exc)
    else:
        raise AssertionError("expected UploadValidationError for oversize upload")


def test_save_resume_base64_rejects_mismatched_type(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    encoded = base64.b64encode(b"plain text").decode("ascii")
    try:
        save_resume_base64("resume.pdf", encoded)
    except UploadValidationError as exc:
        assert "invalid PDF" in str(exc)
    else:
        raise AssertionError("expected UploadValidationError for invalid PDF upload")


def test_predict_with_resume_base64(tmp_path, monkeypatch):
    from scripts.models import RawPost
    from scripts.corpus.store import save_raw_posts

    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/9",
            post_type="text",
            raw_text="面经复盘：一面被拷打。1. 介绍 RAG 项目架构？",
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


def test_resume_extract_api_cleans_uploaded_file(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    encoded = base64.b64encode("项目: RAG LangChain".encode("utf-8")).decode("ascii")
    status, payload = handle_request(
        "POST",
        "/api/resume/extract",
        {"resume_base64": encoded, "resume_filename": "resume.txt"},
    )
    assert status == 200
    assert payload["text"].startswith("项目: RAG")
    assert list(tmp_path.iterdir()) == []


def test_resume_extract_api_text_pdf_boundary_message(tmp_path, monkeypatch):
    import scripts.api.uploads as up

    monkeypatch.setattr(up, "_UPLOAD_DIR", tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "sample_resume.pdf"
    blank_bytes = fixture.read_bytes().replace(b"Skill driven agent project Python RAG", b" ")
    encoded = base64.b64encode(blank_bytes).decode("ascii")
    status, payload = handle_request(
        "POST",
        "/api/resume/extract",
        {"resume_base64": encoded, "resume_filename": "resume.pdf"},
    )
    assert status == 200
    assert payload["text"] == ""
    assert "文本型 PDF" in payload["message"]
    assert list(tmp_path.iterdir()) == []

# --- test_run.py ---

import json


def test_run_role_only_from_raw_posts(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text=(
                "面经复盘：一面被拷打。\n"
                "1. MCP 和 Function Calling 有什么区别？\n"
                "2. RAG 文档切块策略有哪些？\n"
            ),
            posted_at="2026-05-01",
            company="字节跳动",
            role="AI 应用开发",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    cache_dir = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--role",
            "AI 应用开发",
            "--raw-posts",
            str(raw),
            "--cache-dir",
            str(cache_dir),
            "--top-n",
            "10",
            "--refresh",
        ]
    )
    assert code == 0
    banks = list(cache_dir.iterdir())
    assert banks
    bank_file = next(banks[0].glob("question_bank.json"))
    data = json.loads(bank_file.read_text(encoding="utf-8"))
    assert data["question_count"] >= 1
    assert (banks[0] / "frequency_report.md").is_file()


def test_run_with_resume_agent_handoff(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/2",
            post_type="text",
            raw_text="面经复盘：一面被拷打。1. 介绍一下你的 RAG 项目架构？",
            posted_at="2026-05-01",
            company="字节跳动",
            role="AI 应用开发",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    resume = tmp_path / "resume.txt"
    resume.write_text("项目: RAG 知识库 LangChain Python\n技能: Python Redis", encoding="utf-8")
    cache_dir = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--role",
            "AI 应用开发",
            "--resume",
            str(resume),
            "--raw-posts",
            str(raw),
            "--cache-dir",
            str(cache_dir),
            "--refresh",
        ]
    )
    assert code == 0
    slug_dir = next(cache_dir.iterdir())
    assert (slug_dir / "agent_handoff.md").is_file()
    assert (slug_dir / "agent_context.json").is_file()
    assert not (slug_dir / "prep_package.md").is_file()


def test_run_heuristic_prep_package(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/2",
            post_type="text",
            raw_text="面经复盘：一面被拷打。1. 介绍一下你的 RAG 项目架构？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    resume = tmp_path / "resume.txt"
    resume.write_text("项目: RAG LangChain", encoding="utf-8")
    cache_dir = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--role",
            "AI 应用开发",
            "--resume",
            str(resume),
            "--raw-posts",
            str(raw),
            "--cache-dir",
            str(cache_dir),
            "--refresh",
            "--prep-mode",
            "heuristic",
        ]
    )
    assert code == 0
    slug_dir = next(cache_dir.iterdir())
    assert (slug_dir / "prep_package.md").is_file()


def test_run_bank_only_skips_handoff(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/4",
            post_type="text",
            raw_text="面经复盘：一面被拷打。1. 介绍 RAG 架构？",
            posted_at="2026-05-01",
        )
    ]
    raw = tmp_path / "raw.json"
    save_raw_posts(posts, raw)
    cache_dir = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--role",
            "AI 应用开发",
            "--raw-posts",
            str(raw),
            "--cache-dir",
            str(cache_dir),
            "--refresh",
            "--bank-only",
        ]
    )
    assert code == 0
    slug_dir = next(cache_dir.iterdir())
    assert (slug_dir / "question_bank.json").is_file()
    assert not (slug_dir / "agent_handoff.md").is_file()


def test_run_config_from_args_preserves_role_id():
    args = Namespace(
        role="",
        role_id="ai_app",
        resume="",
        companies=[],
        cache_dir="corpus_cache/banks",
        cache_ttl_days=7,
        refresh=False,
        rebuild_only=False,
        raw_posts="",
        from_report=False,
        nowcoder_urls=[],
        discover_nowcoder=False,
        discover_max=50,
        xhs_live=False,
        xhs_deep=True,
        keywords=[],
        top_n=30,
        no_semantic_merge=False,
        merge_threshold=0.72,
        filter_company_questions=False,
        prep_mode="agent",
        no_agent_handoff=False,
        bank_only=False,
        resume_text="",
    )
    config = _config_from_args(args)
    assert config.role_id == "ai_app"
    assert config.role == "AI 应用开发"

# --- test_agent_handoff.py ---

from scripts.agent_handoff import build_agent_context, render_agent_handoff_md, write_agent_handoff
from scripts.models import Question, RawPost


def test_build_agent_context_flags_vision_resume():
    ctx = build_agent_context(
        role="AI 应用开发",
        companies=["字节跳动"],
        posts=[],
        ranked=[Question("RAG 怎么优化?", ["u1"], freq=2, topic="RAG")],
        bank={"role": "AI 应用开发", "question_count": 1, "questions": []},
        paths={"question_bank": "/tmp/bank.json"},
        resume=None,
        resume_text="",
        ingest_mode="ingest",
        sources={},
    )
    assert ctx["prep_mode"] == "agent"
    assert "agent_steps" in ctx
    assert len(ctx["question_candidates"]) == 1


def test_write_agent_handoff_files(tmp_path):
    ctx = {
        "generated_at": "2026-06-18",
        "role": "AI 应用开发",
        "resume": {"text": "Python RAG", "needs_vision": False, "asset_path": ""},
        "posts_needing_vision": [],
        "paths": {},
        "taxonomy": [],
        "question_candidates": [],
        "agent_steps": ["7. 项目锚定"],
        "constraints": ["禁止编造"],
        "outputs_expected": {"prep_package": "corpus_cache/prep_package.md"},
    }
    md, js = write_agent_handoff(tmp_path, "slug1", ctx)
    assert md.is_file()
    assert js.is_file()
    text = md.read_text(encoding="utf-8")
    assert "Agent 交接包" in text
    assert render_agent_handoff_md(ctx).startswith("# Agent")

# --- test_config.py ---

from pathlib import Path

from scripts.config import package_root, resolve_posts_fallback, sample_posts_path
from scripts.doctor import main as doctor_main


def test_sample_posts_bundled():
    path = sample_posts_path()
    assert path.is_file()
    assert path.parent.name == "examples"


def test_resolve_posts_fallback_prefers_user_cache(tmp_path, monkeypatch):
    import scripts.config as cfg

    cache = tmp_path / "corpus_cache"
    cache.mkdir()
    report = cache / "scrape_smoke_report.json"
    report.write_text('{"posts": []}', encoding="utf-8")
    monkeypatch.setattr(cfg, "cache_dir", lambda: cache)
    monkeypatch.chdir(tmp_path)
    assert resolve_posts_fallback() == report


def test_resolve_posts_fallback_sample_when_no_cache(monkeypatch):
    import scripts.config as cfg

    monkeypatch.setattr(cfg, "cache_dir", lambda: Path("/nonexistent/cache"))
    fallback = resolve_posts_fallback()
    assert fallback == sample_posts_path()


def test_load_env_file_does_not_override_existing(tmp_path, monkeypatch):
    import scripts.config as cfg

    env = tmp_path / ".env"
    env.write_text("BOSS_ZHIPIN_COOKIE=from_file\n", encoding="utf-8")
    monkeypatch.setenv("BOSS_ZHIPIN_COOKIE", "from_env")
    cfg._load_env_file(env)
    assert cfg.boss_zhipin_cookie() == "from_env"


def test_load_env_file_sets_when_missing(tmp_path, monkeypatch):
    import scripts.config as cfg

    monkeypatch.delenv("BOSS_ZHIPIN_COOKIE", raising=False)
    monkeypatch.delenv("INTERVIEWRADAR_BOSS_COOKIE", raising=False)
    env = tmp_path / ".env"
    env.write_text("BOSS_ZHIPIN_COOKIE=test_cookie_value_12345\n", encoding="utf-8")
    cfg._load_env_file(env)
    assert cfg.boss_zhipin_cookie() == "test_cookie_value_12345"
    assert cfg.boss_zhipin_cookie_configured()


def test_package_root_is_repo():
    root = package_root()
    assert (root / "README.md").is_file()
    assert (root / "examples" / "sample_raw_posts.json").is_file()


def test_doctor_runs():
    assert doctor_main([]) == 0

# --- test_resume_extract.py ---

from pathlib import Path

from scripts.resume_extract import extract_resume, ResumeExtraction

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.pdf"


def test_pdf_extraction_returns_text():
    result = extract_resume(FIXTURE)
    assert isinstance(result, ResumeExtraction)
    assert "Skill" in result.text
    assert result.needs_vision is False


def test_image_resume_flags_vision(tmp_path):
    img = tmp_path / "resume.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = extract_resume(img)
    assert result.needs_vision is True
    assert result.asset_path == str(img)
    assert result.text == ""


def test_empty_pdf_flags_vision(tmp_path):
    blank = tmp_path / "blank.pdf"
    blank.write_bytes((FIXTURE.read_bytes().replace(b"Skill driven agent project Python RAG", b" ")))
    result = extract_resume(blank)
    assert result.needs_vision is True

# --- test_ocr_extract.py ---

from scripts.ocr.extract import extract_text_from_image, OcrResult


def test_no_engine_flags_vision():
    result = extract_text_from_image("img.png")
    assert isinstance(result, OcrResult)
    assert result.needs_vision is True
    assert result.text == ""
    assert result.confidence == 0.0


def test_confident_engine_returns_text():
    engine = lambda path: ("什么是 RAG？", 0.95)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is False
    assert result.text == "什么是 RAG？"
    assert result.confidence == 0.95


def test_low_confidence_flags_vision_but_keeps_hint():
    engine = lambda path: ("blurry guess", 0.30)
    result = extract_text_from_image("img.png", engine=engine, min_confidence=0.6)
    assert result.needs_vision is True
    assert result.text == "blurry guess"


def test_empty_text_flags_vision_even_if_confident():
    engine = lambda path: ("", 0.99)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is True


def test_xhs_scrape_safe_uses_core_keywords(monkeypatch):
    captured: dict = {}

    def fake_scrape(keywords, **kwargs):
        captured["keywords"] = keywords
        captured["kwargs"] = kwargs
        return {"ok": True, "keywords": keywords, "export_path": "/tmp/x.json"}

    monkeypatch.setattr("scripts.scrape.xhs_export.run_safe_xhs_scrape", fake_scrape)
    status, payload = handle_request(
        "POST",
        "/api/xhs/scrape-safe",
        {"role_id": "data", "core_only": True, "companies": []},
    )
    assert status == 200
    assert "数开面经" in captured["keywords"]
    assert "数据开发 实习 面经" not in captured["keywords"]
    assert payload.get("mode") == "core_only"


def test_xhs_scrape_plan_core_pool():
    from scripts.scrape.xhs_scrape_plan import plan_xhs_scrape_batch

    batch, pause, batch_size, meta = plan_xhs_scrape_batch(
        "data",
        [],
        core_only=True,
        rotate=False,
        keywords_per_day=26,
    )
    assert len(batch) == 26
    assert meta["mode"] == "core_only"
    assert batch_size >= 2
    assert pause >= 12
