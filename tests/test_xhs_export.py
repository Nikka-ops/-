import json
from pathlib import Path

from scripts.scrape.normalize_xhs import normalize
from scripts.scrape.xhs_export import _merge_notes_from_files, collect_xhs_export_files


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
        "scripts.scrape.xhs_export.mediacrawler_home",
        lambda: tmp_path / "empty_mc",
    )
    paths = collect_xhs_export_files(max_age_days=30)
    assert export in paths
