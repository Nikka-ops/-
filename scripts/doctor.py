#!/usr/bin/env python3
"""Environment check for new contributors / users."""
from __future__ import annotations

import importlib.util
import sys

from scripts import __version__
from scripts.config import (
    boss_cdp_enabled,
    boss_cdp_port,
    boss_zhipin_cookie_configured,
    spider_xhs_home,
    package_root,
    resolve_posts_fallback,
    sample_posts_path,
)


def _ok(msg: str) -> str:
    return f"  ✓ {msg}"


def _warn(msg: str) -> str:
    return f"  ⚠ {msg}"


def _fail(msg: str) -> str:
    return f"  ✗ {msg}"


def main(argv: list[str] | None = None) -> int:
    del argv
    lines = [f"InterviewRadar {__version__}", f"Package root: {package_root()}", ""]
    ok = True

    if sys.version_info < (3, 11):
        lines.append(_fail(f"Python {sys.version_info.major}.{sys.version_info.minor} — need 3.11+"))
        ok = False
    else:
        lines.append(_ok(f"Python {sys.version_info.major}.{sys.version_info.minor}"))

    for mod in ("pypdf", "requests", "bs4", "rapidocr", "onnxruntime"):
        if importlib.util.find_spec(mod) is None:
            lines.append(_fail(f"Missing dependency: {mod} (pip install -e .)"))
            ok = False
        else:
            lines.append(_ok(f"import {mod}"))

    sample = sample_posts_path()
    if sample.is_file():
        lines.append(_ok(f"Demo corpus: {sample}"))
    else:
        lines.append(_fail(f"Demo corpus missing: {sample}"))
        ok = False

    fallback = resolve_posts_fallback()
    if fallback:
        lines.append(_ok(f"Default ingest fallback: {fallback}"))
    else:
        lines.append(_warn("No local corpus yet — use examples/sample_raw_posts.json or scrape"))

    home = spider_xhs_home()
    if (home / "apis" / "xhs_pc_apis.py").is_file():
        node_ok = (home / "node_modules").is_dir()
        extra = "" if node_ok else " (run: cd ~/.spider_xhs && npm install)"
        lines.append(_ok(f"Spider_XHS found: {home}{extra}"))
    else:
        lines.append(
            _warn(
                f"Spider_XHS not at {home} — clone: "
                "git clone https://github.com/cv-cat/Spider_XHS.git ~/.spider_xhs"
            )
        )

    from scripts.config import xhs_web_session_configured
    from scripts.scrape.xhs_export import xhs_scrape_status

    xhs = xhs_scrape_status()
    if xhs_web_session_configured():
        lines.append(_ok(f"XHS cookies configured ({xhs.get('cookie_source', 'env')})"))
    else:
        lines.append(
            _warn("XHS cookies not configured — login in CDP Chrome or set XHS_COOKIES; see docs/setup/spider_xhs.md")
        )
    export_n = xhs.get("export_files", 0)
    if export_n:
        latest = xhs.get("latest_export_at") or "unknown time"
        lines.append(_ok(f"XHS local JSON exports: {export_n} file(s), latest {latest}"))
    else:
        lines.append(
            _warn(
                "No recent XHS JSON exports — run: "
                "uv run python -m scripts.tools.xhs_scrape_safe --role-id ai_app"
            )
        )

    if boss_zhipin_cookie_configured():
        lines.append(_ok("Boss直聘 Cookie: configured (.env or env)"))
    else:
        lines.append(
            _warn("Boss直聘 Cookie: not set — CDP 或见 docs/setup/boss-zhipin-cookie.md")
        )

    if boss_cdp_enabled():
        lines.append(_ok(f"Boss CDP: port {boss_cdp_port()} listening"))
    else:
        lines.append(
            _warn(
                f"Boss CDP: not listening on {boss_cdp_port()} "
                "(optional: bash scripts/tools/start-boss-cdp-chrome.sh)"
            )
        )

    from scripts.scrape.schedule_info import daily_schedule_status

    sched = daily_schedule_status()
    if sched.get("active"):
        lines.append(
            _ok(
                f"Daily scrape scheduler: {sched.get('scheduler')} active "
                f"(last run {sched.get('last_daily_run') or 'never'})"
            )
        )
    elif sched.get("scheduler"):
        lines.append(_warn(f"Daily scrape scheduler: {sched.get('scheduler')} not active"))
    else:
        lines.append(
            _warn(
                "Daily scrape scheduler: not installed — "
                "python -m scripts.tools.install_daily_schedule"
            )
        )

    lines.extend(
        [
            "",
            "Quick demo:",
            "  interview-radar --role \"AI 应用开发\" --from-report \\",
            "    --raw-posts examples/sample_raw_posts.json",
            "",
            "Web UI:",
            "  interview-radar-web --port 8765",
        ]
    )
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
