"""Consolidated: test_nowcoder_connector.py, test_xiaohongshu_connector.py, test_github_connector.py, test_base_connector.py, test_job_pro_connector.py"""


# --- test_nowcoder_connector.py ---

from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.nowcoder import parse_nowcoder_post, NowCoderConnector

FIXTURE = Path(__file__).parent / "fixtures" / "nowcoder_sample.html"
SAMPLE_HTML = FIXTURE.read_text(encoding="utf-8")


def test_parse_extracts_text_and_date():
    post = parse_nowcoder_post(SAMPLE_HTML, "https://nowcoder.com/p/1")
    assert post.source == "nowcoder"
    assert post.url == "https://nowcoder.com/p/1"
    assert post.posted_at == "2025-09-20"
    assert "MCP 和 Skill 的区别" in post.raw_text
    assert "agent 项目架构" in post.raw_text
    assert "字节 AI 应用开发 一面面经" in post.raw_text
    assert post.company == "字节跳动"
    assert post.role == "Agent 开发"


def test_connector_search_uses_injected_fetcher():
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"],
        fetcher=lambda url: SAMPLE_HTML,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 1
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("login wall")

    conn = NowCoderConnector(post_urls=["https://nowcoder.com/p/1"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "cookie" in result.message.lower()


def test_parse_handles_nc_post_content_selector():
    html = (
        "<div class='content-post-title'><h1>【面试真题】字节 AI 应用岗</h1></div>"
        "<div class='nc-post-content'><p>问了 MCP 和 Agent 兜底策略。</p></div>"
        '<script>{"createTime":1758326400000}</script>'
    )
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/new")
    assert "MCP 和 Agent 兜底策略" in post.raw_text
    assert post.company == "字节跳动"
    assert post.role == "Agent 开发"


def test_parse_missing_date_yields_none():
    html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body text here</p></div>"
    )
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/2")
    assert post.posted_at is None
    assert "body text here" in post.raw_text
    assert post.raw_text.startswith("T")


def test_connector_degrades_when_parsed_content_is_empty():
    drift_html = "<html><body><div class='something-else'>nothing useful</div></body></html>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"], fetcher=lambda url: drift_html
    )
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "selector" in result.message.lower()


def test_connector_degrades_when_majority_bodies_empty_keeps_good_posts():
    # Real-world case: NowCoder serves anti-bot pages where createTime stays in the
    # JS blob but the editor content div is missing. Most posts come back empty;
    # we should flag this loud (status=degraded) but keep whatever did parse.
    good_html = (
        "<div class='content-post-title'><h1>真实标题</h1></div>"
        "<div class='nc-slate-editor-content'><p>真实正文</p></div>"
        "<script>{\"createTime\":1758326400000}</script>"
    )
    empty_html = "<script>{\"createTime\":1758326400000}</script>"  # createTime survives, body gone

    def fetch(url):
        return good_html if url.endswith("/1") else empty_html

    conn = NowCoderConnector(
        post_urls=[f"https://nowcoder.com/p/{i}" for i in range(1, 5)],  # 1 good + 3 empty
        fetcher=fetch,
    )
    result = conn.search([])
    assert result.status == "degraded"
    assert "anti-bot" in result.message.lower() or "重试" in result.message
    assert len(result.posts) == 1
    assert "真实正文" in result.posts[0].raw_text


def test_connector_ok_when_minority_bodies_empty():
    # 1 empty out of 4 (25%) — under the 50% threshold, treat as ok and keep all posts
    good_html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body</p></div>"
        "<script>{\"createTime\":1758326400000}</script>"
    )
    empty_html = "<script>{\"createTime\":1758326400000}</script>"

    def fetch(url):
        return empty_html if url.endswith("/4") else good_html

    conn = NowCoderConnector(
        post_urls=[f"https://nowcoder.com/p/{i}" for i in range(1, 5)],
        fetcher=fetch,
    )
    result = conn.search([])
    assert result.status == "ok"
    assert len(result.posts) == 4


def test_parse_handles_only_title_or_only_content():
    title_only_html = "<div class='content-post-title'><h1>仅标题</h1></div>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/3"], fetcher=lambda url: title_only_html
    )
    result = conn.search([])
    assert result.status == "ok"
    assert result.posts[0].raw_text == "仅标题"

    content_only_html = "<div class='nc-slate-editor-content'><p>正文段落</p></div>"
    conn2 = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/4"], fetcher=lambda url: content_only_html
    )
    result2 = conn2.search([])
    assert result2.status == "ok"
    assert "正文段落" in result2.posts[0].raw_text

# --- test_xiaohongshu_connector.py ---

import json
from pathlib import Path

import pytest

from scripts.connectors.base import SearchResult
from scripts.connectors.xiaohongshu import (
    parse_mediacrawler_export,
    XiaohongshuConnector,
)
from scripts.scrape.spider_xhs_driver import SpiderXHSDriver

FIXTURE = Path(__file__).parent / "fixtures" / "xhs_mediacrawler_export.json"
SAMPLE_JSON = FIXTURE.read_text(encoding="utf-8")


def test_parse_maps_notes_to_image_rawposts():
    posts = parse_mediacrawler_export(SAMPLE_JSON)
    assert len(posts) == 2
    first = posts[0]
    assert first.source == "xiaohongshu"
    assert first.url == "https://www.xiaohongshu.com/explore/n1"
    assert first.post_type == "image"
    assert first.posted_at == "2025-09-20"
    assert first.asset_paths == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]
    assert "MCP 和 Skill 的区别" in first.raw_text
    assert "字节 AI 应用开发 面经" in first.raw_text


def test_parse_zero_time_yields_none_date():
    posts = parse_mediacrawler_export(SAMPLE_JSON)
    assert posts[1].posted_at is None


def test_connector_search_uses_injected_loader():
    conn = XiaohongshuConnector(
        export_path="whatever.json",
        loader=lambda p: SAMPLE_JSON,
        enable_image_ocr=False,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 2
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_when_loader_fails():
    def boom(path):
        raise FileNotFoundError("no export")

    conn = XiaohongshuConnector(export_path="missing.json", loader=boom, enable_image_ocr=False)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "spider" in result.message.lower() or "小红书" in result.message


def test_connector_requires_export_path_or_driver():
    with pytest.raises(ValueError):
        XiaohongshuConnector()


def _make_driver_fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "spider_xhs"
    (home / "apis").mkdir(parents=True)
    (home / "data" / "xhs" / "json").mkdir(parents=True)
    (home / "apis" / "xhs_pc_apis.py").write_text("# stub")
    (home / "node_modules").mkdir()
    return home


def test_connector_driver_mode_scrapes_and_returns_posts(tmp_path: Path, monkeypatch):
    home = _make_driver_fake_home(tmp_path)
    export_notes = [
        {
            "note_id": "n1",
            "note_url": "https://www.xiaohongshu.com/explore/n1",
            "title": "AI Agent 面经",
            "desc": "字节一面问了 MCP",
            "time": 1758326400000,
            "image_list": ["https://x.example/img1.jpg"],
            "tags": [],
        }
    ]
    out_path = home / "data" / "xhs" / "json" / "search_contents_2026-06-01.json"

    class FakeDriver:
        def scrape_xhs(self, keywords, **kwargs):
            out_path.write_text(json.dumps(export_notes), encoding="utf-8")
            return out_path

    conn = XiaohongshuConnector(driver=FakeDriver(), enable_image_ocr=False)
    result = conn.search(["AI Agent"])

    assert result.status == "ok"
    assert len(result.posts) == 1
    post = result.posts[0]
    assert post.source == "xiaohongshu"
    assert "MCP" in post.raw_text
    assert post.asset_paths == ["https://x.example/img1.jpg"]


def test_connector_driver_mode_degrades_on_scrape_failure(tmp_path: Path):
    class BoomDriver:
        def scrape_xhs(self, keywords, **kwargs):
            raise RuntimeError("login expired")

    conn = XiaohongshuConnector(driver=BoomDriver(), enable_image_ocr=False)
    result = conn.search(["foo"])

    assert result.status == "degraded"
    assert result.posts == []
    assert "login" in result.message.lower() or "小红书" in result.message


def test_connector_driver_mode_requires_queries(tmp_path: Path):
    class FakeDriver:
        def scrape_xhs(self, keywords, **kwargs):
            raise AssertionError("should not scrape")

    conn = XiaohongshuConnector(driver=FakeDriver(), enable_image_ocr=False)
    result = conn.search([])

    assert result.status == "degraded"
    assert "关键词" in result.message

# --- test_github_connector.py ---

from scripts.connectors.base import SearchResult
from scripts.connectors.github import extract_posts_from_markdown, GithubConnector


SAMPLE_MD = """# Agent 面经
## 一面
- 说明 MCP 和 Skill 的区别
- 什么是 RAG？
随便一句不是题目的话。
### 项目相关
1. 介绍一下你的 agent 项目架构
"""


def test_extract_picks_question_like_lines():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    texts = [p.raw_text for p in posts]
    assert "说明 MCP 和 Skill 的区别" in texts
    assert "什么是 RAG？" in texts
    assert "介绍一下你的 agent 项目架构" in texts
    assert "随便一句不是题目的话。" not in texts


def test_extract_sets_source_and_url():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    assert all(p.source == "github" for p in posts)
    assert all(p.url == "https://example.com/repo" for p in posts)
    assert all(p.post_type == "text" for p in posts)


def test_connector_search_uses_injected_fetcher():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert any("RAG" in p.raw_text for p in result.posts)


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("network down")

    conn = GithubConnector(repo_raw_urls=["https://example.com/repo"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []


def test_extract_with_hints_keeps_only_matching():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["RAG"],
    )
    texts = [p.raw_text for p in posts]
    assert "什么是 RAG？" in texts
    assert "说明 MCP 和 Skill 的区别" not in texts
    assert "介绍一下你的 agent 项目架构" not in texts


def test_extract_with_hints_case_insensitive():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["mcp"],  # lowercase, candidate has uppercase MCP
    )
    texts = [p.raw_text for p in posts]
    assert any("MCP" in t for t in texts)
    assert all("RAG" not in t for t in texts)


def test_extract_with_empty_hints_does_not_filter():
    posts_none = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=None)
    posts_empty = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=[])
    assert {p.raw_text for p in posts_none} == {p.raw_text for p in posts_empty}
    assert len(posts_empty) >= 3  # all question-like lines


def test_connector_passes_hints_through():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
        relevance_hints=["agent"],
    )
    result = conn.search([])
    assert result.status == "ok"
    texts = [p.raw_text for p in result.posts]
    assert any("agent" in t.lower() for t in texts)
    assert all("RAG" not in t for t in texts)


def test_extract_with_empty_string_hint_does_not_match_all():
    # Defensive: a stray empty-string hint must not turn into "match everything"
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["", "RAG"],
    )
    texts = [p.raw_text for p in posts]
    assert "什么是 RAG？" in texts
    assert "说明 MCP 和 Skill 的区别" not in texts

# --- test_base_connector.py ---

from scripts.models import RawPost
from scripts.connectors.base import Connector, SearchResult


def test_searchresult_holds_status_and_posts():
    posts = [RawPost("github", "u1", "text", "Q1")]
    r = SearchResult(posts=posts, status="ok", message="")
    assert r.posts == posts
    assert r.status == "ok"


def test_searchresult_degraded_factory_has_no_posts():
    r = SearchResult.degraded("nowcoder", "needs cookie")
    assert r.posts == []
    assert r.status == "degraded"
    assert "cookie" in r.message


def test_connector_is_abstract():
    class Dummy(Connector):
        name = "dummy"

        def search(self, queries):
            return SearchResult(posts=[], status="ok", message="")

    assert Dummy().search(["x"]).status == "ok"

# --- test_job_pro_connector.py ---

import json
from pathlib import Path

from scripts.jobs.connectors.job_pro import JobProConnector, _position_to_job

FIXTURE_FIND = Path(__file__).parent / "fixtures" / "job_pro_find.json"


def test_position_to_job():
    pos = {
        "post_id": "1",
        "title": "后端开发",
        "work_cities": "北京",
        "apply_url": "https://example.com/j/1",
        "project": "技术",
        "recruit_label": "正式",
    }
    detail = {
        "description": "做后端服务",
        "requirements": "熟悉 Java",
    }
    job = _position_to_job("tencent", pos, detail=detail)
    assert job is not None
    assert job.company == "腾讯"
    assert job.source == "job_pro:tencent"
    assert "做后端服务" in job.description
    assert "熟悉 Java" in job.description


def test_job_pro_connector_multi_company_with_injected_runner():
    payload = json.loads(FIXTURE_FIND.read_text(encoding="utf-8"))
    block_by_key = {b["company"]: b for b in payload["results"]}

    def runner(cmd):
        assert "search" in cmd
        key = next((p for p in cmd if p in block_by_key), None)
        block = block_by_key.get(key or "")
        if not block:
            return json.dumps({"ok": False, "message": "missing"})
        return json.dumps(
            {
                "ok": True,
                "positions": block.get("positions") or [],
            }
        )

    conn = JobProConnector(
        company_keys=["tencent", "bytedance"],
        runner=runner,
    )
    result = conn.search(["AI应用"], max_per_query=10)
    assert result.status == "ok"
    assert len(result.jobs) == 2
    companies = {j.company for j in result.jobs}
    assert "腾讯" in companies
    assert "字节跳动" in companies
