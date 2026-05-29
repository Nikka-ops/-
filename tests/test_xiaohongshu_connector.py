from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.xiaohongshu import (
    parse_mediacrawler_export,
    XiaohongshuConnector,
)

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
    conn = XiaohongshuConnector(export_path="whatever.json", loader=lambda p: SAMPLE_JSON)
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 2
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_when_loader_fails():
    def boom(path):
        raise FileNotFoundError("no export")

    conn = XiaohongshuConnector(export_path="missing.json", loader=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "mediacrawler" in result.message.lower()
