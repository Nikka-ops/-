"""Consolidated: test_daily_scrape.py, test_normalize_xhs.py, test_xhs_export.py, test_xhs_session_config.py, test_xhs_image_processing.py, test_mediacrawler_driver.py, test_discover_nowcoder.py, test_nowcoder_detail.py, test_nowcoder_moments.py, test_net_retry.py, test_local_assets.py"""


# --- test_daily_scrape.py ---

import sys
from datetime import date, timedelta
from unittest.mock import patch

from scripts.corpus.company_catalog import all_preset_companies, resolve_company_list
from scripts.scrape.schedule_info import daily_schedule_status, run_daily_entrypoint
from scripts.tools.full_scrape import _stage_counts
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.scrape_state import (
    append_rolling_nowcoder_posts,
    filter_new_nowcoder_posts,
    load_scrape_state,
    pick_nowcoder_query_batch,
    pick_xhs_keyword_batch,
    save_scrape_state,
)
from scripts.models import RawPost
from scripts.tools.run_daily_scrape import _acquire_lock, _release_lock


def test_resolve_company_list_all():
    names = resolve_company_list("all")
    assert len(names) == len(all_preset_companies())
    assert "字节跳动" in names


def test_xhs_keyword_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    keywords = ["a", "b", "c", "d", "e"]
    state = load_scrape_state()
    b1 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b1 == ["a", "b"]
    b2 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b2 == ["c", "d"]
    b3 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b3 == ["e", "a"]


def test_nowcoder_query_stale_after_day():
    state = {"query_last_run": {"q1": (date.today() - timedelta(days=2)).isoformat()}}
    batch = pick_nowcoder_query_batch(["q1", "q2"], state, per_day=5, min_days_between=1)
    assert "q1" in batch


def test_filter_and_append_rolling_nowcoder(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    state = load_scrape_state()
    p1 = RawPost(source="nowcoder", url="https://www.nowcoder.com/feed/main/detail/u1", post_type="text", raw_text="a")
    p2 = RawPost(source="nowcoder", url="https://www.nowcoder.com/feed/main/detail/u2", post_type="text", raw_text="b")
    new_only = filter_new_nowcoder_posts([p1, p2], state)
    assert len(new_only) == 2
    again = filter_new_nowcoder_posts([p1], state)
    assert len(again) == 0
    assert append_rolling_nowcoder_posts(new_only) == 2
    assert append_rolling_nowcoder_posts([p1]) == 0


def test_xhs_keywords_for_data_role():
    from scripts.corpus.company_catalog import all_preset_companies

    keys = xhs_keywords_for_role("data", all_preset_companies())
    assert "数开面经" in keys
    assert "数开一面" in keys
    assert "数仓面经" in keys
    assert "数据开发 面经" in keys
    assert "大数据开发面经" in keys
    assert "字节跳动 数开面经" in keys
    assert len(keys) < 200
    assert all("面经" in k or "一面" in k or "二面" in k or "三面" in k for k in keys)


def test_xhs_keywords_for_ai_app_all_companies():
    keys = xhs_keywords_for_role("ai_app", all_preset_companies())
    assert len(keys) >= 100
    assert all("面经" in k for k in keys)


def test_stage_counts_role_and_recency():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/feed/main/detail/a",
            post_type="text",
            raw_text="字节跳动 AI 应用开发 面经 RAG Agent",
            posted_at="2026-06-01",
        ),
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/feed/main/detail/b",
            post_type="text",
            raw_text="纯后端 Java 八股",
            posted_at="2026-06-01",
        ),
    ]
    stages = _stage_counts(posts, "AI 应用开发", 90)
    assert stages["raw"] == 2
    assert stages["after_role_filter"] >= 1
    assert stages["after_recency"] >= 1


def test_run_daily_scrape_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("scripts.tools.run_daily_scrape._log_dir", lambda: tmp_path / "daily")
    (tmp_path / "daily").mkdir(parents=True)
    assert _acquire_lock()
    assert not _acquire_lock()
    _release_lock()
    assert _acquire_lock()
    _release_lock()


def test_install_daily_schedule_help():
    from scripts.tools.install_daily_schedule import main

    with patch.object(sys, "argv", ["install_daily_schedule", "--help"]):
        try:
            main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0


def test_run_daily_entrypoint():
    assert "run_daily_scrape" in run_daily_entrypoint()


def test_daily_schedule_status_shape():
    info = daily_schedule_status()
    assert "platform" in info
    assert "install_hint" in info
    assert "active" in info
    assert "scheduler" in info

# --- test_normalize_xhs.py ---

import json
from pathlib import Path

from scripts.connectors.xiaohongshu import parse_mediacrawler_export
from scripts.scrape.normalize_xhs import _main, normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mc_xhs_raw.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_skips_notes_with_no_id_and_no_url():
    out = normalize(_load())
    assert len(out) == 4
    assert "garbage" not in {n["desc"] for n in out}


def test_passes_through_normal_note():
    out = normalize(_load())
    first = out[0]
    assert first["note_id"] == "n1"
    assert first["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    assert first["title"] == "字节 AI 应用开发 面经"
    assert first["desc"].startswith("一面")
    assert first["time"] == 1758326400000
    assert first["image_list"] == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]


def test_splits_comma_image_list_and_strips_empties():
    out = normalize(_load())
    n2 = next(n for n in out if n["note_id"] == "n2")
    assert n2["image_list"] == [
        "https://sns-img.xhs.cn/n2_a.jpg",
        "https://sns-img.xhs.cn/n2_b.jpg",
    ]


def test_synthesizes_url_from_note_id_when_url_missing():
    out = normalize(_load())
    n3 = next(n for n in out if n["note_id"] == "n3")
    assert n3["note_url"] == "https://www.xiaohongshu.com/explore/n3"


def test_drops_unknown_keys_but_preserves_tags():
    out = normalize(_load())
    first = out[0]
    assert "liked_count" not in first
    assert "comments" not in first
    assert "tag_list" not in first
    assert "type" not in first
    assert first["tags"] == ["面经", "实习"]


def test_invalid_time_becomes_zero_and_null_image_list_becomes_empty():
    out = normalize(_load())
    n5 = next(n for n in out if n["note_id"] == "n5")
    assert n5["time"] == 0
    assert n5["image_list"] == []
    assert n5["title"] == ""
    assert n5["desc"] == ""


def test_preserves_input_order():
    out = normalize(_load())
    assert [n["note_id"] for n in out] == ["n1", "n2", "n3", "n5"]


def test_cli_writes_normalized_file(tmp_path, capsys):
    out_path = tmp_path / "xhs_export.json"
    rc = _main([str(FIXTURE), "-o", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(written, list) and len(written) == 4
    assert written[0]["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    assert "wrote 4 notes" in capsys.readouterr().out


def test_end_to_end_with_plan3_connector(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.connectors.xiaohongshu.full_scrape_recency_days", lambda: 9999)
    out_path = tmp_path / "xhs_export.json"
    _main([str(FIXTURE), "-o", str(out_path)])
    posts = parse_mediacrawler_export(out_path.read_text(encoding="utf-8"))
    assert len(posts) == 4
    n1 = posts[0]
    assert n1.source == "xiaohongshu"
    assert n1.post_type == "image"
    assert n1.posted_at == "2025-09-20"
    assert n1.asset_paths == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]
    n2 = next(p for p in posts if "RAG" in p.raw_text)
    assert n2.posted_at is None

# --- test_xhs_export.py ---

import json
from pathlib import Path

from scripts.scrape.normalize_xhs import normalize
from scripts.scrape.xhs_export import (
    _merge_notes_from_files,
    collect_xhs_export_files,
    load_xhs_posts_from_exports,
)


def test_merge_notes_dedupes_by_note_id(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    note = {
        "note_id": "n1",
        "title": "面经",
        "desc": "body",
        "time": 1700000000000,
        "image_list": [],
    }
    a.write_text(json.dumps([note]), encoding="utf-8")
    b.write_text(json.dumps([note, {"note_id": "n2", "title": "t2", "desc": "d2"}]), encoding="utf-8")
    merged = _merge_notes_from_files([a, b])
    assert len(merged) == 2


def test_collect_xhs_export_files_from_cache(tmp_path, monkeypatch):
    xhs_dir = tmp_path / "xhs"
    xhs_dir.mkdir()
    export = xhs_dir / "search_contents_2026-06-01.json"
    export.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("scripts.scrape.xhs_export.cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.scrape.xhs_export.spider_xhs_home",
        lambda: tmp_path / "empty_mc",
    )
    paths = collect_xhs_export_files(max_age_days=30)
    assert export in paths


def test_load_xhs_posts_from_exports_meta(tmp_path, monkeypatch):
    spider_home = tmp_path / "spider"
    xhs_dir = spider_home / "data" / "xhs" / "json"
    xhs_dir.mkdir(parents=True)
    note = {
        "note_id": "n1",
        "title": "字节数开一面凉经",
        "desc": "1. Spark shuffle\n2. Hive 分区",
        "time": 1700000000000,
        "image_list": [],
        "note_url": "https://www.xiaohongshu.com/explore/n1",
    }
    export = xhs_dir / "search_contents_2026-06-24.json"
    export.write_text(json.dumps([note]), encoding="utf-8")
    monkeypatch.setattr("scripts.scrape.xhs_export.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("scripts.scrape.xhs_export.spider_xhs_home", lambda: spider_home)
    posts, meta = load_xhs_posts_from_exports(enable_ocr=False, max_age_days=30)
    assert meta["post_count_before_recency"] == 1
    assert len(posts) == 1
    assert "数开" in posts[0].raw_text


def test_spider_xhs_461_hint():
    from scripts.scrape.spider_xhs_driver import _HTTP_461_HINT

    assert "461" in _HTTP_461_HINT

# --- test_xhs_session_config.py ---

from scripts.config import (
    _xhs_web_session_from_mediancrawler,
    xhs_web_session,
    xhs_web_session_configured,
    xhs_web_session_source,
)


def test_xhs_session_from_mediancrawler_config(tmp_path, monkeypatch):
    mc = tmp_path / "mediacrawler"
    cfg = mc / "config"
    cfg.mkdir(parents=True)
    (cfg / "base_config.py").write_text(
        'COOKIES = "web_session=abcdef0123456789abcdef01"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("XHS_WEB_SESSION", raising=False)
    monkeypatch.delenv("INTERVIEWRADAR_XHS_WEB_SESSION", raising=False)
    monkeypatch.setenv("MEDIACRAWLER_HOME", str(mc))

    assert _xhs_web_session_from_mediancrawler() == "abcdef0123456789abcdef01"
    assert xhs_web_session() == "abcdef0123456789abcdef01"
    assert xhs_web_session_configured()
    assert xhs_web_session_source() == "mediacrawler:legacy"


def test_xhs_session_env_overrides_mediancrawler(tmp_path, monkeypatch):
    mc = tmp_path / "mediacrawler"
    cfg = mc / "config"
    cfg.mkdir(parents=True)
    (cfg / "base_config.py").write_text(
        'COOKIES = "web_session=from_mc_only_value_12345"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDIACRAWLER_HOME", str(mc))
    monkeypatch.setenv("XHS_WEB_SESSION", "from_env_session_value_123456")

    assert xhs_web_session() == "from_env_session_value_123456"
    assert xhs_web_session_source() == "env:XHS_WEB_SESSION"

# --- test_xhs_image_processing.py ---

import json
from pathlib import Path

from scripts.connectors.xiaohongshu import XiaohongshuConnector
from scripts.ocr.xhs_images import (
    PageMerger,
    XHSAssetDownloader,
    XHSImageOCRProcessor,
    process_xhs_note_images,
)


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_downloader_preserves_image_order_and_names_pages(tmp_path):
    seen_urls = []

    def fake_get(url, timeout=None, **kwargs):
        seen_urls.append(url)
        return FakeResponse(f"bytes:{url}".encode("utf-8"))

    downloader = XHSAssetDownloader(asset_root=tmp_path, http_get=fake_get)
    paths = downloader.download(
        "n1",
        ["https://img.example/a.png", "https://img.example/b.webp", "https://img.example/c"],
    )

    assert seen_urls == [
        "https://img.example/a.png",
        "https://img.example/b.webp",
        "https://img.example/c",
    ]
    assert [p.name for p in paths] == ["001.png", "002.webp", "003.jpg"]
    assert [p.parent.name for p in paths] == ["n1", "n1", "n1"]


def test_page_merger_keeps_page_boundaries_in_order():
    text = PageMerger().merge(["第一页题目", "第二页追问"])
    assert text == "[图片 OCR 第 1 页]\n第一页题目\n\n[图片 OCR 第 2 页]\n第二页追问"


def test_process_uses_image_ocr_as_primary_content_not_caption(tmp_path):
    image_paths = []

    def fake_get(url, timeout=None, **kwargs):
        return FakeResponse(b"img")

    def engine(path):
        image_paths.append(Path(path).name)
        return (f"{Path(path).stem} OCR 问题", 0.92)

    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="阿里系面经",
        desc="希望帮到大家 #面经",
        tags=["阿里", "大模型"],
        image_urls=["https://img.example/one.jpg", "https://img.example/two.jpg"],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=fake_get,
        ocr_engine=engine,
    )

    assert image_paths == ["001.jpg", "002.jpg"]
    assert post.locator_text == "阿里系面经\n希望帮到大家 #面经\n阿里 大模型"
    assert "[图片 OCR 第 1 页]\n001 OCR 问题" in post.image_ocr_text
    assert "001 OCR 问题" in post.raw_text
    assert "希望帮到大家" in post.raw_text
    assert "[图片 OCR 第 1 页]" not in post.raw_text
    assert post.content_text == post.raw_text
    assert post.asset_paths == [
        str(tmp_path / "assets" / "n1" / "001.jpg"),
        str(tmp_path / "assets" / "n1" / "002.jpg"),
    ]
    assert post.extraction_quality == "ocr_ok"
    assert post.needs_vision_fallback is False


def test_process_marks_low_quality_ocr_without_mixing_caption(tmp_path):
    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="阿里系面经",
        desc="caption 干扰文本",
        tags=[],
        image_urls=["https://img.example/one.jpg"],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=lambda url, timeout=None, **kwargs: FakeResponse(b"img"),
        ocr_engine=lambda path: ("短", 0.2),
    )

    assert "caption 干扰文本" in post.raw_text
    assert "[图片 OCR 第 1 页]" not in post.raw_text
    assert post.needs_vision_fallback is True
    assert post.extraction_quality == "ocr_low_quality"


def test_process_without_images_falls_back_to_locator_text(tmp_path):
    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="标题",
        desc="正文",
        tags=[],
        image_urls=[],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
    )

    assert post.raw_text == "标题\n正文"
    assert post.content_text == "标题\n正文"
    assert post.locator_text == "标题\n正文"
    assert post.image_ocr_text is None
    assert post.extraction_quality == "text_only"


def test_connector_integrates_downloader_ocr_and_primary_content(tmp_path):
    sample = [
        {
            "note_id": "n1",
            "note_url": "https://www.xiaohongshu.com/explore/n1",
            "title": "阿里系面经",
            "desc": "caption 不进主正文",
            "time": 1758326400000,
            "image_list": ["https://img.example/one.jpg"],
            "tag_list": ["阿里", "面经"],
        }
    ]
    conn = XiaohongshuConnector(
        export_path="whatever.json",
        loader=lambda path: json.dumps(sample, ensure_ascii=False),
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=lambda url, timeout=None, **kwargs: FakeResponse(b"img"),
        ocr_engine=lambda path: ("自我介绍\nagent 项目拷打", 0.95),
    )

    result = conn.search(["阿里"])

    assert result.status == "ok"
    post = result.posts[0]
    assert "自我介绍" in post.raw_text
    assert "agent 项目拷打" in post.raw_text
    assert "[图片 OCR 第 1 页]" not in post.raw_text
    assert "caption 不进主正文" in post.raw_text
    assert "caption 不进主正文" in post.locator_text
    assert post.asset_paths == [str(tmp_path / "assets" / "n1" / "001.jpg")]
    assert post.extraction_quality == "ocr_ok"

# --- test_spider_xhs_driver.py ---

from scripts.scrape.spider_xhs_driver import SpiderXHSNotInstalledError, SpiderXHSDriver, _detect_home
from scripts.scrape.spider_xhs_normalize import note_from_handled, note_from_search_item


def test_detect_home_defaults_to_dot_spider_xhs(monkeypatch):
    monkeypatch.delenv("SPIDER_XHS_HOME", raising=False)
    assert _detect_home() == Path.home() / ".spider_xhs"


def test_note_from_search_item_display_title():
    item = {
        "id": "abc",
        "model_type": "note",
        "xsec_token": "tok",
        "note_card": {
            "display_title": "数据开发一面",
            "desc": "问了 Spark",
            "type": "normal",
            "image_list": [],
            "tag_list": [{"name": "面经"}],
        },
    }
    note = note_from_search_item(item)
    assert note["note_id"] == "abc"
    assert note["title"] == "数据开发一面"
    assert "tok" in note["note_url"]


def test_note_from_handled_maps_upload_time():
    handled = {
        "note_id": "n1",
        "note_url": "https://xhs/n1",
        "title": "t",
        "desc": "d",
        "upload_time": "2025-09-20 12:00:00",
        "image_list": ["http://img/1.jpg"],
        "tags": ["面经"],
    }
    note = note_from_handled(handled)
    assert note["time"] > 0
    assert note["image_list"] == ["http://img/1.jpg"]


def test_spider_driver_requires_install(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.scrape.spider_xhs_driver.resolve_xhs_cookies",
        lambda: "web_session=abcdefghijklmnopqrstuvwxyz0123456789",
    )
    with pytest.raises(SpiderXHSNotInstalledError):
        SpiderXHSDriver(home=tmp_path / "missing").scrape_xhs(["数据开发 面经"])

# --- test_discover_nowcoder.py ---

from scripts.discover.nowcoder_urls import (
    discover_nowcoder_urls,
    extract_nowcoder_urls_from_html,
    normalize_nowcoder_discuss_url,
)

SAMPLE_HTML = """
<html><body>
<a href="https://www.nowcoder.com/discuss/882634966025175040">面经1</a>
<a href="//www.nowcoder.com/discuss/881209147377664000">面经2</a>
<a href="https://www.nowcoder.com/discuss/list">skip list</a>
</body></html>
"""


def test_normalize_nowcoder_discuss_url():
    assert (
        normalize_nowcoder_discuss_url("https://www.nowcoder.com/discuss/123")
        == "https://www.nowcoder.com/discuss/123"
    )
    assert normalize_nowcoder_discuss_url("https://www.nowcoder.com/discuss/list") is None


def test_extract_nowcoder_urls_from_html():
    urls = extract_nowcoder_urls_from_html(SAMPLE_HTML)
    assert urls == [
        "https://www.nowcoder.com/discuss/882634966025175040",
        "https://www.nowcoder.com/discuss/881209147377664000",
    ]


def test_discover_nowcoder_urls_dedupes_and_limits():
    def fake_fetcher(query: str) -> str:
        return SAMPLE_HTML

    urls, meta = discover_nowcoder_urls(
        ["AI 应用开发 面经", "Agent 面经"],
        max_per_query=1,
        search_fetcher=fake_fetcher,
        request_delay=0,
    )
    assert len(urls) == 2
    assert meta["count"] == 2

# --- test_nowcoder_detail.py ---

from scripts.corpus.post_format import format_body_html, split_body_lines, strip_duplicate_title
from scripts.discover.nowcoder_detail import fetch_nowcoder_moment_full, needs_full_fetch


def test_split_inline_numbered_lines():
    raw = "前言 1.第一点 2.第二点 3.第三点"
    lines = split_body_lines(raw)
    assert any("第一点" in ln for ln in lines)
    assert any(ln.startswith("2") for ln in lines)


def test_strip_duplicate_title():
    body = strip_duplicate_title("字节测开面经", "字节测开面经\n1.问题一")
    assert body.startswith("1.")


def test_format_body_skips_duplicate_title():
    html = format_body_html("字节测开面经\n1.问题一\n2.问题二", title="字节测开面经")
    assert "字节测开面经" not in html or html.count("字节") == 0
    assert "问题一" in html


def test_needs_full_fetch_on_ellipsis():
    assert needs_full_fetch("1. aaa…2. bbb")
    assert not needs_full_fetch("1. aaa\n2. bbb\n3. ccc")


def test_fetch_nowcoder_moment_full_live():
    text = fetch_nowcoder_moment_full("f65b692f76244441a53cecb6f435fcc6", use_cache=True)
    assert "RAG" in text or "幻觉" in text
    assert "…" not in text or text.count("\n") >= 5

# --- test_nowcoder_moments.py ---

from scripts.discover.nowcoder_moments import moment_to_raw_post, search_nowcoder_moments


def test_moment_to_raw_post():
    moment = {
        "id": 2859824,
        "uuid": "f054aef412104109a1dfa85e273e6faf",
        "title": "福州朴朴科技-算法工程师暑期实习-面经",
        "content": "1. 介绍项目\n2. 深度学习基础",
        "createdAt": 1780393247000,
    }
    post = moment_to_raw_post(moment)
    assert post is not None
    assert post.source == "nowcoder"
    assert "算法工程师" in post.raw_text
    assert "feed/main/detail" in post.url
    assert post.posted_at


def test_moment_from_content_data():
    from scripts.discover.nowcoder_moments import _moment_dict_from_payload, moment_to_raw_post

    payload = {
        "contentData": {
            "id": "888446465431830528",
            "uuid": "921b42b28fcf45d5bd63baa7489d048c",
            "title": "Ai Agent、ai应用开发面经面试题2",
            "content": "RAG 延迟优化与多路召回 …",
            "createTime": 1780393247000,
            "contentImageUrls": [],
        }
    }
    moment = _moment_dict_from_payload(payload)
    assert moment is not None
    post = moment_to_raw_post(moment)
    assert post is not None
    assert "RAG" in post.raw_text


def test_iter_search_payloads_skips_list_data():
    from scripts.discover.nowcoder_moments import _iter_search_payloads

    assert _iter_search_payloads({"data": [{"id": 1}]}) == [{"id": 1}]
    assert _iter_search_payloads({"data": {"momentData": {"id": 2}}}) == [{"momentData": {"id": 2}}]
    assert _iter_search_payloads({"data": None}) == []


def test_search_nowcoder_moments_live():
    posts, meta = search_nowcoder_moments(["算法工程师面经"], max_per_query=2, request_delay=0)
    assert meta["count"] == len(posts)
    assert len(posts) >= 1
    assert all(p.raw_text for p in posts)

# --- test_net_retry.py ---

import pytest
import requests

from scripts.net.retry import is_retryable_http_error, retry_call


def test_is_retryable_timeout():
    assert is_retryable_http_error(requests.Timeout())


def test_retry_call_succeeds_after_failure():
    calls = 0

    def flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise requests.Timeout()
        return "ok"

    assert retry_call(flaky, attempts=3, backoff=(0.0, 0.0)) == "ok"
    assert calls == 2


def test_retry_call_raises_non_retryable():
    with pytest.raises(ValueError):
        retry_call(lambda: (_ for _ in ()).throw(ValueError("bad")), attempts=3, backoff=(0.0, 0.0))

# --- test_local_assets.py ---

from pathlib import Path

from scripts.corpus.post_format import (
    _local_assets_for_post_url,
    _resolve_local_asset_path,
    collect_image_urls,
)


def test_collect_image_urls_includes_local_asset(tmp_path, monkeypatch):
    assets = tmp_path / "corpus_cache" / "assets" / "posts" / "n1"
    assets.mkdir(parents=True)
    img = assets / "001.jpg"
    img.write_bytes(b"fakejpeg")
    monkeypatch.chdir(tmp_path)

    rel = "corpus_cache/assets/posts/n1/001.jpg"
    urls = collect_image_urls({"asset_paths": [rel]})
    assert urls == [rel]
    assert _resolve_local_asset_path(rel) == rel


def test_local_assets_for_post_url(tmp_path, monkeypatch):
    import hashlib

    url = "https://www.xiaohongshu.com/explore/abc123?xsec_token=foo"
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    folder = tmp_path / "corpus_cache" / "assets" / "posts" / key
    folder.mkdir(parents=True)
    (folder / "001.jpg").write_bytes(b"jpeg")
    monkeypatch.chdir(tmp_path)

    rels = _local_assets_for_post_url(url)
    assert len(rels) == 1
    assert rels[0].endswith("001.jpg")


def test_resolve_local_asset_path_rejects_outside_assets(tmp_path, monkeypatch):
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _resolve_local_asset_path(str(outside)) is None
