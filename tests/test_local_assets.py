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
