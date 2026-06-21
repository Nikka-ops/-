import json
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.corpus.bank_cache import (
    bank_slug,
    is_fresh,
    list_banks,
    load_bank_bundle,
    load_question_bank,
    meta_path,
    question_bank_path,
    save_bank_artifacts,
    write_meta,
)
from scripts.corpus.export_bank import build_question_bank, render_frequency_report
from scripts.models import Question, RawPost
from scripts.corpus.store import save_raw_posts


def test_bank_slug_stable():
    a = bank_slug("AI 应用开发", ["字节跳动", "美团"])
    b = bank_slug("AI 应用开发", ["美团", "字节跳动"])
    assert a == b
    assert "AI" in a or "应用" in a


def test_is_fresh_respects_ttl(tmp_path: Path):
    slug = bank_slug("后端", [])
    write_meta(
        tmp_path,
        slug,
        role="后端",
        companies=[],
        post_count=1,
        question_count=2,
        sources={},
    )
    meta = json.loads(meta_path(tmp_path, slug).read_text(encoding="utf-8"))
    meta["updated_at"] = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    meta_path(tmp_path, slug).write_text(json.dumps(meta), encoding="utf-8")
    assert is_fresh(tmp_path, slug, ttl_days=7, today=date.today())

    meta["updated_at"] = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    meta_path(tmp_path, slug).write_text(json.dumps(meta), encoding="utf-8")
    assert not is_fresh(tmp_path, slug, ttl_days=7, today=date.today())


def test_save_and_paths(tmp_path: Path):
    slug = bank_slug("Agent", ["字节跳动"])
    posts = [
        RawPost(
            source="x",
            url="u",
            post_type="text",
            raw_text="1. Agent 记忆怎么设计？",
            company="字节跳动",
        )
    ]
    save_raw_posts(posts, tmp_path / slug / "raw_posts.json")
    assert (tmp_path / slug / "raw_posts.json").is_file()
    write_meta(
        tmp_path,
        slug,
        role="Agent",
        companies=["字节跳动"],
        post_count=1,
        question_count=1,
        sources={},
    )
    assert question_bank_path(tmp_path, slug).parent.is_dir()


def test_list_and_load_bank_bundle(tmp_path: Path):
    slug = bank_slug("AI 应用开发", [])
    ranked = [
        Question(
            "RAG 怎么优化？",
            source_refs=["https://example.com/1"],
            freq=2,
            topic="RAG",
            company_tags=["字节跳动"],
        )
    ]
    bank = build_question_bank(
        role="AI 应用开发",
        companies=[],
        ranked=ranked,
        post_count=3,
        sources_meta={"demo": True},
    )
    report = render_frequency_report(bank)
    posts = [
        RawPost(
            source="nowcoder",
            url="https://example.com/1",
            post_type="text",
            raw_text="字节 RAG 面经\n1. 怎么优化？",
            company="字节跳动",
            role="AI 应用开发",
        )
    ]
    save_bank_artifacts(tmp_path, slug, posts, ranked, bank, report)
    write_meta(
        tmp_path,
        slug,
        role="AI 应用开发",
        companies=[],
        post_count=3,
        question_count=1,
        sources={"demo": True},
    )
    listed = list_banks(tmp_path)
    assert len(listed) == 1
    assert listed[0]["slug"] == slug
    bundle = load_bank_bundle(tmp_path, slug)
    assert bundle is not None
    assert bundle["bank"]["question_count"] == 1
    assert len(bundle["posts"]) == 1
    assert bundle["companies"][0]["name"] == "字节跳动"
    assert "RAG" in bundle["frequency_report"]
    assert load_question_bank(tmp_path, slug)["role"] == "AI 应用开发"
    assert load_bank_bundle(tmp_path, "missing") is None
