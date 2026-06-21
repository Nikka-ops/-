from pathlib import Path

from scripts.corpus.bank_cache import load_merged_role_bundle


def test_load_merged_role_bundle_combines_ai_app_banks(tmp_path):
    root = Path(__file__).resolve().parents[1] / "corpus_cache" / "banks"
    if not root.is_dir():
        return
    bundle = load_merged_role_bundle(root, "AI 应用开发", role_id="ai_app")
    assert bundle is not None
    assert len(bundle["posts"]) >= 8
    assert len(bundle.get("merged_slugs") or []) >= 2
    with_img = sum(1 for p in bundle["posts"] if p.get("has_images") or p.get("image_urls"))
    assert with_img >= 5
