import sys
from pathlib import Path
from unittest.mock import patch

from scripts.tools.run_daily_scrape import _acquire_lock, _release_lock


def test_run_daily_scrape_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("scripts.tools.run_daily_scrape._log_dir", lambda: tmp_path / "daily")
    (tmp_path / "daily").mkdir(parents=True)

    assert _acquire_lock()
    assert not _acquire_lock()
    _release_lock()
    assert _acquire_lock()
    _release_lock()


def test_install_daily_schedule_help():
    from scripts.tools.install_daily_schedule import main

    with patch.object(sys, "argv", ["install_daily_schedule", "--help"]):
        try:
            main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
