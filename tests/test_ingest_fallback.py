from pathlib import Path

import pytest

from scripts.corpus.ingest_fallback import (
    build_ingest_failure_message,
    corpus_matches_role,
    ingest_attempted_live,
    resolve_role_aware_fallback,
    role_mismatch_warning,
)
from scripts.config import sample_posts_path
from scripts.models import RawPost
from scripts.service import RunConfig, ingest_posts


def test_corpus_matches_role_ai_app_from_queries():
    hints = ["AI 应用开发 面经", "字节跳动 AI 应用开发 面经"]
    assert corpus_matches_role("AI 应用开发", hints)
    assert corpus_matches_role("AI应用开发", hints)


def test_corpus_does_not_match_backend_for_ai_queries():
    hints = ["AI 应用开发 面经", "字节跳动 Agent开发 面经"]
    assert not corpus_matches_role("后端开发", hints)


def test_resolve_role_aware_fallback_skips_mismatched_report(tmp_path, monkeypatch):
    report = tmp_path / "scrape_smoke_report.json"
    report.write_text(
        '{"queries":["AI 应用开发 面经"],"posts":[{"source":"xiaohongshu","url":"u","post_type":"text","raw_text":"RAG Agent 项目","role":"Agent开发"}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    assert resolve_role_aware_fallback("AI 应用开发") == report
    assert resolve_role_aware_fallback("后端开发") is None


def test_ingest_attempted_live_flags():
    assert ingest_attempted_live(RunConfig(role="x", discover_nowcoder=True))
    assert ingest_attempted_live(RunConfig(role="x", nowcoder_urls=["https://nowcoder.com/discuss/1"]))
    assert not ingest_attempted_live(
        RunConfig(role="x", raw_posts="a.json", discover_nowcoder=False),
    )


def test_ingest_no_silent_fallback_on_failed_live(tmp_path, monkeypatch):
    banks = tmp_path / "banks"
    report = tmp_path / "scrape_smoke_report.json"
    report.write_text(
        '{"queries":["AI 应用开发 面经"],"posts":[{"source":"xiaohongshu","url":"u","post_type":"text","raw_text":"RAG 项目","posted_at":"2026-05-01"}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    config = RunConfig(
        role="后端开发",
        cache_dir=str(banks),
        refresh=True,
        discover_nowcoder=True,
        discover_max_per_query=1,
        xhs_use_export=False,
    )

    monkeypatch.setattr(
        "scripts.service.discover_nowcoder_urls",
        lambda queries, **kwargs: ([], {"count": 0, "per_query": []}),
    )
    monkeypatch.setattr(
        "scripts.service.search_nowcoder_moments",
        lambda queries, **kwargs: ([], {"count": 0}),
    )

    with pytest.raises(FileNotFoundError, match="未抓到任何面经帖"):
        ingest_posts(config, ["后端开发 面经"])


def test_role_mismatch_warning_on_explicit_raw(tmp_path):
    raw = tmp_path / "demo.json"
    raw.write_text(
        '[{"source":"nowcoder","url":"u","post_type":"text","raw_text":"RAG","role":"AI 应用开发","posted_at":"2026-05-01"}]',
        encoding="utf-8",
    )
    msg = role_mismatch_warning("后端开发", raw)
    assert msg and "不匹配" in msg


def test_ingest_uses_role_matched_fallback_without_live(tmp_path, monkeypatch):
    banks = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "scripts.service.discover_nowcoder_urls",
        lambda queries, **kwargs: ([], {"count": 0, "per_query": []}),
    )
    monkeypatch.setattr(
        "scripts.service.search_nowcoder_moments",
        lambda queries, **kwargs: ([], {"count": 0}),
    )

    config = RunConfig(
        role="AI 应用开发",
        cache_dir=str(banks),
        refresh=True,
        discover_nowcoder=False,
        xhs_use_export=False,
    )
    posts, meta, _ = ingest_posts(config, ["AI 应用开发 面经"])
    assert len(posts) >= 1
    assert meta["sources"].get("fallback") == str(sample_posts_path())


def test_build_ingest_failure_message_mentions_live():
    config = RunConfig(role="后端开发", discover_nowcoder=True)
    msg = build_ingest_failure_message("后端开发", config, ["后端开发 面经"])
    assert "不会自动改用" in msg
    assert "discover-nowcoder" in msg or "自动发现" in msg
