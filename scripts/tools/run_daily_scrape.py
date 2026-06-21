#!/usr/bin/env python3
"""Cross-platform daily scrape runner (lock, logs, venv bootstrap)."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.config import bootstrap_env, cache_dir, package_root

LOCK_NAME = ".daily_scrape.lock"


def _log_dir() -> Path:
    d = cache_dir() / "daily"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    path = _log_dir() / "cron.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _project_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _ensure_venv(root: Path) -> Path:
    py = _project_python(root)
    if py.is_file():
        return py
    _append_log("installing venv …")
    if sys.platform == "win32":
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "install.ps1")],
            cwd=str(root),
            check=False,
        )
    else:
        subprocess.run(["bash", str(root / "install.sh")], cwd=str(root), check=False)
    if not py.is_file():
        raise FileNotFoundError(f"Python venv not found at {py}")
    return py


def _acquire_lock() -> bool:
    lock = _log_dir() / LOCK_NAME
    try:
        lock.mkdir(exist_ok=False)
        return True
    except OSError:
        return False


def _release_lock() -> None:
    lock = _log_dir() / LOCK_NAME
    try:
        lock.rmdir()
    except OSError:
        pass


def run_daily_scrape_once() -> int:
    bootstrap_env()
    root = package_root()
    os.chdir(root)

    if not _acquire_lock():
        _append_log("skip: another daily scrape is running")
        return 0

    role_id = os.environ.get("INTERVIEWRADAR_DAILY_ROLE_ID", "ai_app")
    role_ids = os.environ.get("INTERVIEWRADAR_DAILY_ROLE_IDS", "").strip()
    companies = os.environ.get("INTERVIEWRADAR_DAILY_COMPANIES", "all")

    try:
        py = _ensure_venv(root)
        log_role = role_ids or role_id
        _append_log(f"daily scrape start roles={log_role} companies={companies}")

        cmd = [
            str(py),
            "-m",
            "scripts.tools.daily_scrape",
            "--companies",
            companies,
            "--json",
        ]
        if role_ids:
            cmd.extend(["--role-ids", role_ids])
        else:
            cmd.extend(["--role-id", role_id])

        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        last_run = _log_dir() / "last_run.json"
        if proc.stdout:
            last_run.write_text(proc.stdout, encoding="utf-8")
        if proc.stderr:
            with (_log_dir() / "cron.log").open("a", encoding="utf-8") as fh:
                fh.write(proc.stderr)
        _append_log(f"daily scrape exit {proc.returncode}")
        return int(proc.returncode)
    finally:
        _release_lock()


def main(argv: list[str] | None = None) -> int:
    del argv
    code = run_daily_scrape_once()
    if code not in (0, 1):
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
