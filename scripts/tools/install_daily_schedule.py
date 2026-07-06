#!/usr/bin/env python3
"""Install / uninstall cross-platform daily scrape scheduler (macOS / Windows / Linux)."""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from scripts.config import cache_dir, focus_role_ids_csv, package_root

LABEL = "com.interviewradar.daily-scrape"
PLIST_NAME = f"{LABEL}.plist"
WINDOWS_TASK_NAME = "InterviewRadar Daily Scrape"
CRON_MARKER = "InterviewRadar-daily-scrape"


def _project_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs, check=False)


def _ensure_venv(root: Path) -> Path:
    py = _project_python(root)
    if py.is_file():
        return py
    if sys.platform == "win32":
        install_ps1 = root / "install.ps1"
        if install_ps1.is_file():
            _run_cmd(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install_ps1)],
                cwd=str(root),
            )
    else:
        install_sh = root / "install.sh"
        if install_sh.is_file():
            _run_cmd(["bash", str(install_sh)], cwd=str(root))
    if not py.is_file():
        raise FileNotFoundError(f"venv python missing: {py}")
    return py


def _runner_module() -> str:
    return "scripts.tools.run_daily_scrape"


def install_macos(hour: int, minute: int, role_id: str, role_ids: str, root: Path, py: Path) -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / PLIST_NAME
    log_dir = cache_dir() / "daily"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{escape(LABEL)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{escape(str(py))}</string>
    <string>-m</string>
    <string>{escape(_runner_module())}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{escape(str(root))}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>INTERVIEWRADAR_DAILY_ROLE_ID</key>
    <string>{escape(role_id)}</string>
    <key>INTERVIEWRADAR_DAILY_ROLE_IDS</key>
    <string>{escape(role_ids)}</string>
    <key>INTERVIEWRADAR_DAILY_COMPANIES</key>
    <string>all</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Minute</key>
    <integer>{minute}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>{escape(str(log_dir / "launchd.out.log"))}</string>
  <key>StandardErrorPath</key>
  <string>{escape(str(log_dir / "launchd.err.log"))}</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
"""
    plist_path.write_text(content, encoding="utf-8")
    uid = os.getuid()
    domain = f"gui/{uid}/{LABEL}"
    _run_cmd(["launchctl", "bootout", domain])
    _run_cmd(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)])
    _run_cmd(["launchctl", "enable", domain])


def uninstall_macos() -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / PLIST_NAME
    uid = os.getuid()
    domain = f"gui/{uid}/{LABEL}"
    _run_cmd(["launchctl", "bootout", domain])
    _run_cmd(["launchctl", "disable", domain])
    if plist_path.is_file():
        plist_path.unlink()


def install_windows(hour: int, minute: int, role_id: str, role_ids: str, root: Path, py: Path) -> None:
    st = f"{hour:02d}:{minute:02d}"
    role_env = (
        f'set INTERVIEWRADAR_DAILY_ROLE_IDS={role_ids} && '
        if role_ids
        else f"set INTERVIEWRADAR_DAILY_ROLE_ID={role_id} && "
    )
    tr = (
        f'cmd /c "cd /d {root} && {role_env}'
        f'set INTERVIEWRADAR_DAILY_COMPANIES=all && "{py}" -m {_runner_module()}"'
    )
    _run_cmd(["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"])
    proc = _run_cmd(
        [
            "schtasks",
            "/Create",
            "/TN",
            WINDOWS_TASK_NAME,
            "/TR",
            tr,
            "/SC",
            "DAILY",
            "/ST",
            st,
            "/F",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"schtasks failed: {err}")


def uninstall_windows() -> None:
    _run_cmd(["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"])


def _read_crontab() -> list[str]:
    proc = _run_cmd(["crontab", "-l"], capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _write_crontab(lines: list[str]) -> None:
    content = "\n".join(lines) + "\n"
    proc = _run_cmd(["crontab", "-"], input=content, text=True, capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(f"crontab update failed: {err}")


def install_linux_cron(hour: int, minute: int, role_id: str, role_ids: str, root: Path, py: Path) -> None:
    role_env = (
        f"INTERVIEWRADAR_DAILY_ROLE_IDS={role_ids} "
        if role_ids
        else f"INTERVIEWRADAR_DAILY_ROLE_ID={role_id} "
    )
    line = (
        f"{minute} {hour} * * * cd {root} && "
        f"{role_env}"
        f"INTERVIEWRADAR_DAILY_COMPANIES=all "
        f"{py} -m {_runner_module()} # {CRON_MARKER}"
    )
    lines = [ln for ln in _read_crontab() if CRON_MARKER not in ln]
    lines.append(line)
    _write_crontab(lines)


def uninstall_linux_cron() -> None:
    lines = [ln for ln in _read_crontab() if CRON_MARKER not in ln]
    _write_crontab(lines)


def install(hour: int, minute: int, role_id: str, role_ids: str) -> None:
    root = package_root()
    py = _ensure_venv(root)
    system = platform.system()

    if system == "Darwin":
        install_macos(hour, minute, role_id, role_ids, root, py)
        scheduler = "launchd (macOS)"
    elif system == "Windows":
        install_windows(hour, minute, role_id, role_ids, root, py)
        scheduler = "Task Scheduler (Windows)"
    else:
        install_linux_cron(hour, minute, role_id, role_ids, root, py)
        scheduler = "cron (Linux)"

    log_dir = cache_dir() / "daily"
    role_desc = role_ids or role_id
    print(f"✓ 已安装每日自动抓取 · {scheduler}")
    print(f"  时间: 每天 {hour:02d}:{minute:02d}")
    print(f"  岗位: {role_desc} · 公司: 全国大厂 (all)")
    print(f"  日志: {log_dir / 'cron.log'}")
    print(f"  试跑: python -m scripts.tools.run_daily_scrape")
    print(f"  卸载: python -m scripts.tools.install_daily_schedule --uninstall")


def uninstall() -> None:
    system = platform.system()
    if system == "Darwin":
        uninstall_macos()
    elif system == "Windows":
        uninstall_windows()
    else:
        uninstall_linux_cron()
    print("✓ 已卸载每日自动抓取任务")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InterviewRadar 跨平台每日调度安装")
    parser.add_argument("--hour", type=int, default=8, help="每天执行小时 (0-23)")
    parser.add_argument("--minute", type=int, default=0, help="分钟 (0-59)")
    parser.add_argument("--role-id", default="data")
    parser.add_argument(
        "--role-ids",
        default=focus_role_ids_csv(),
        help="逗号分隔多岗位（设置 INTERVIEWRADAR_DAILY_ROLE_IDS，覆盖 --role-id）",
    )
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    if not 0 <= args.hour <= 23 or not 0 <= args.minute <= 59:
        print("hour/minute out of range", file=sys.stderr)
        return 1

    role_ids = args.role_ids.strip() or focus_role_ids_csv()
    role_id = args.role_id.strip() or (role_ids.split(",")[0] if role_ids else "data")

    try:
        if args.uninstall:
            uninstall()
        else:
            install(args.hour, args.minute, role_id, role_ids)
    except (OSError, RuntimeError, FileNotFoundError) as exc:
        print(f"安装失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
