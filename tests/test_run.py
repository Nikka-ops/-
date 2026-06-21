import json
from pathlib import Path

from scripts.models import RawPost
from scripts.corpus.store import save_raw_posts
from scripts.run import main


def test_run_role_only_from_raw_posts(tmp_path: Path, monkeypatch):
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/1",
            post_type="text",
            raw_text=(
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
            raw_text="1. 介绍一下你的 RAG 项目架构？",
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
            raw_text="1. 介绍一下你的 RAG 项目架构？",
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
            raw_text="1. 介绍 RAG 架构？",
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
