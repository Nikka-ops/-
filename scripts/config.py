"""Environment-backed paths for open-source / local installs."""
from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ (does not override existing vars)."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if val and val[0] in {"'", '"'} and val[-1] == val[0]:
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


def bootstrap_env() -> None:
    """Load optional .env from repo root and current working directory."""
    for base in (_PKG_ROOT, Path.cwd()):
        _load_env_file(base / ".env")


def package_root() -> Path:
    return _PKG_ROOT


def app_display_name() -> str:
    """Label shown in Cursor browser tabs / background usage attribution."""
    return (
        os.environ.get("INTERVIEWRADAR_DISPLAY_NAME")
        or os.environ.get("APP_DISPLAY_NAME")
        or "data_agent_adar"
    ).strip() or "data_agent_adar"


def cache_dir() -> Path:
    raw = os.environ.get("INTERVIEWRADAR_CACHE_DIR")
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else Path.cwd() / p
    for base in (Path.cwd(), package_root()):
        candidate = base / "corpus_cache"
        if candidate.is_dir():
            return candidate
    return package_root() / "corpus_cache"


def banks_dir() -> Path:
    return cache_dir() / "banks"


def jobs_dir() -> Path:
    return cache_dir() / "jobs"


def boss_zhipin_cookie() -> str:
    """Cookie string for Boss直聘 wapi (user-exported from browser)."""
    return (
        os.environ.get("BOSS_ZHIPIN_COOKIE")
        or os.environ.get("INTERVIEWRADAR_BOSS_COOKIE")
        or ""
    ).strip()


def boss_zhipin_cookie_configured() -> bool:
    return len(boss_zhipin_cookie()) > 20


def boss_cdp_port() -> int:
    raw = os.environ.get("BOSS_CDP_PORT", "9222").strip()
    try:
        return int(raw)
    except ValueError:
        return 9222


def boss_cdp_enabled() -> bool:
    """Explicit CDP mode or auto when CDP port is listening."""
    if os.environ.get("BOSS_CDP", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    from scripts.jobs.cdp_client import cdp_port_open

    return cdp_port_open(boss_cdp_port())


def mediacrawler_home() -> Path:
    env = os.environ.get("MEDIACRAWLER_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mediacrawler"


def xhs_web_session() -> str:
    """`web_session` cookie value for Xiaohongshu (paste from browser DevTools)."""
    return (
        os.environ.get("XHS_WEB_SESSION")
        or os.environ.get("INTERVIEWRADAR_XHS_WEB_SESSION")
        or ""
    ).strip()


def xhs_web_session_configured() -> bool:
    return len(xhs_web_session()) > 20


def xhs_batch_pause_seconds() -> float:
    raw = os.environ.get("XHS_BATCH_PAUSE_SECONDS", "60").strip()
    try:
        return max(15.0, float(raw))
    except ValueError:
        return 60.0


def xhs_max_keywords_per_run() -> int:
    raw = os.environ.get("XHS_MAX_KEYWORDS_PER_RUN", "8").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 8


def xhs_export_max_age_days() -> int:
    raw = os.environ.get("XHS_EXPORT_MAX_AGE_DAYS", "365").strip()
    try:
        return max(7, min(730, int(raw)))
    except ValueError:
        return 365


def xhs_export_max_files() -> int:
    raw = os.environ.get("XHS_EXPORT_MAX_FILES", "120").strip()
    try:
        return max(5, min(500, int(raw)))
    except ValueError:
        return 120


def xhs_crawler_max_notes() -> int:
    """MediaCrawler CRAWLER_MAX_NOTES_COUNT (per keyword)."""
    raw = os.environ.get("XHS_CRAWLER_MAX_NOTES", "80").strip()
    try:
        return max(15, min(200, int(raw)))
    except ValueError:
        return 80


def full_scrape_recency_days() -> int:
    raw = os.environ.get("FULL_SCRAPE_RECENCY_DAYS", "365").strip()
    try:
        return max(30, min(730, int(raw)))
    except ValueError:
        return 365


def company_aliases_path() -> Path:
    """YAML config for subsidiary → parent company normalization."""
    raw = os.environ.get("COMPANY_ALIASES_PATH", "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else package_root() / p
    return package_root() / "config" / "company_aliases.yaml"


def deepseek_api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def deepseek_api_base() -> str:
    raw = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").strip()
    return raw.rstrip("/")


def deepseek_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"


def post_ai_filter_enabled() -> bool:
    raw = os.environ.get("POST_AI_FILTER", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(deepseek_api_key())


def post_ai_filter_max_chars() -> int:
    raw = os.environ.get("POST_AI_FILTER_MAX_CHARS", "900").strip()
    try:
        return max(200, min(4000, int(raw)))
    except ValueError:
        return 900


def sample_posts_path() -> Path:
    """Bundled demo corpus — works offline without scraping."""
    env = os.environ.get("INTERVIEWRADAR_SAMPLE_POSTS")
    if env:
        p = Path(env).expanduser()
        return p if p.is_absolute() else package_root() / p
    return package_root() / "examples" / "sample_raw_posts.json"


def sample_resume_path() -> Path:
    return package_root() / "examples" / "sample_resume.txt"


def list_ingest_fallback_candidates() -> list[Path]:
    """Local corpora that ingest may use when role matches (see ingest_fallback)."""
    out: list[Path] = []
    for candidate in (
        cache_dir() / "scrape_smoke_report.json",
        sample_posts_path(),
    ):
        if candidate.is_file():
            out.append(candidate)
    return out


def resolve_posts_fallback() -> Path | None:
    """First existing local corpus path (for status/doctor — not role-filtered)."""
    candidates = list_ingest_fallback_candidates()
    return candidates[0] if candidates else None


bootstrap_env()
