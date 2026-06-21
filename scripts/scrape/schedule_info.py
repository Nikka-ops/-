"""Detect local daily scrape scheduler (launchd / Task Scheduler / cron)."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from scripts.config import cache_dir, package_root

LABEL = "com.interviewradar.daily-scrape"
PLIST_NAME = f"{LABEL}.plist"
WINDOWS_TASK_NAME = "InterviewRadar Daily Scrape"
CRON_MARKER = "InterviewRadar-daily-scrape"


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / PLIST_NAME


def run_daily_entrypoint() -> str:
    return "python -m scripts.tools.run_daily_scrape"


def _launchd_loaded() -> bool:
    try:
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _windows_task_installed() -> bool:
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", WINDOWS_TASK_NAME],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _linux_cron_installed() -> bool:
    try:
        proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5, check=False)
        if proc.returncode != 0:
            return False
        return CRON_MARKER in proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def daily_schedule_status() -> dict:
    log_dir = cache_dir() / "daily"
    state_path = log_dir / "scrape_state.json"
    last_run = log_dir / "last_run.json"
    cron_log = log_dir / "cron.log"
    system = platform.system()

    info: dict = {
        "platform": system,
        "run_entrypoint": run_daily_entrypoint(),
        "log_dir": str(log_dir),
        "state_path": str(state_path) if state_path.is_file() else None,
        "last_run_json": str(last_run) if last_run.is_file() else None,
        "cron_log": str(cron_log) if cron_log.is_file() else None,
        "install_hint": "python -m scripts.tools.install_daily_schedule",
    }

    scheduler = None
    active = False

    if system == "Darwin":
        plist = launchd_plist_path()
        info["launchd_plist"] = str(plist)
        info["launchd_installed"] = plist.is_file()
        info["launchd_loaded"] = plist.is_file() and _launchd_loaded()
        if info["launchd_installed"]:
            scheduler = "launchd"
            active = info["launchd_loaded"]
    elif system == "Windows":
        info["windows_task_name"] = WINDOWS_TASK_NAME
        info["windows_task_installed"] = _windows_task_installed()
        if info["windows_task_installed"]:
            scheduler = "schtasks"
            active = True
    else:
        info["cron_marker"] = CRON_MARKER
        info["cron_installed"] = _linux_cron_installed()
        if info["cron_installed"]:
            scheduler = "cron"
            active = True

    info["scheduler"] = scheduler
    info["active"] = active

    if state_path.is_file():
        try:
            import json

            state = json.loads(state_path.read_text(encoding="utf-8"))
            info["last_daily_run"] = state.get("last_daily_run")
            info["xhs_queue_offset"] = state.get("xhs_queue_offset")
        except (OSError, json.JSONDecodeError):
            pass

    if info.get("last_daily_run") is None and last_run.is_file():
        try:
            import json

            run = json.loads(last_run.read_text(encoding="utf-8"))
            info["last_daily_run"] = run.get("date")
        except (OSError, json.JSONDecodeError):
            pass

    return info
