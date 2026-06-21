from pathlib import Path

from scripts.config import package_root, resolve_posts_fallback, sample_posts_path


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
