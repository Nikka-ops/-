"""Shell-out driver for MediaCrawler 小红书 search.

Assumes:
- MediaCrawler is cloned at $MEDIACRAWLER_HOME (env var) or ~/.mediacrawler/
- User has run `python main.py --platform xhs --lt qrcode --type search ...`
  at least once and scanned the QR code; login state is cached by
  MediaCrawler at its own login_state location
- MediaCrawler's xhs search writes notes JSON to
  `<home>/data/xhs/json/search_contents_*.json`

If MediaCrawler changes its CLI or output layout, only this file needs to be
touched.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class MediaCrawlerNotInstalledError(FileNotFoundError):
    pass


class MediaCrawlerScrapeError(RuntimeError):
    pass


@dataclass
class _Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _default_runner(cmd: list[str], cwd: Path, timeout: int) -> _Result:
    proc = subprocess.run(
        cmd, cwd=str(cwd), timeout=timeout, capture_output=True, text=True, check=False
    )
    return _Result(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _detect_home() -> Path:
    env = os.environ.get("MEDIACRAWLER_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mediacrawler"


class MediaCrawlerDriver:
    """Drives MediaCrawler from this skill. Login is the user's job; everything
    after login (scrape + locate output JSON) is automated by this driver."""

    def __init__(
        self,
        home: Path | None = None,
        runner: Callable[[list[str], Path, int], _Result] | None = None,
    ):
        self.home = (home or _detect_home()).expanduser()
        if not self.home.is_dir():
            raise MediaCrawlerNotInstalledError(
                f"MediaCrawler not found at {self.home}. "
                "Install it (https://github.com/NanmiCoder/MediaCrawler) and "
                "either set $MEDIACRAWLER_HOME or clone to ~/.mediacrawler/."
            )
        self.runner = runner or _default_runner

    @property
    def output_dir(self) -> Path:
        return self.home / "data" / "xhs" / "json"

    def scrape_xhs(self, keywords: list[str], timeout: int = 600) -> Path:
        """Run MediaCrawler xhs search and return the path to the freshly-produced
        notes JSON.

        Raises MediaCrawlerScrapeError on non-zero exit, missing output, or any
        other observable failure. Login expiry typically shows up as a non-zero
        exit; surface the message so the user knows to re-scan the QR code.
        """
        if not keywords:
            raise ValueError("keywords must be non-empty")

        cmd = [
            "python",
            str(self.home / "main.py"),
            "--platform",
            "xhs",
            "--lt",
            "qrcode",
            "--type",
            "search",
            "--keywords",
            ",".join(keywords),
        ]

        out_dir = self.output_dir
        existing = set(out_dir.glob("search_contents_*.json")) if out_dir.is_dir() else set()

        try:
            result = self.runner(cmd, self.home, timeout)
        except subprocess.TimeoutExpired as exc:
            raise MediaCrawlerScrapeError(
                f"MediaCrawler did not finish within {timeout}s; "
                "anti-bot challenge or hanging session?"
            ) from exc

        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-500:]
            raise MediaCrawlerScrapeError(
                f"MediaCrawler exited {result.returncode}. "
                "Common causes: login expired (re-scan QR), anti-bot block, "
                f"or CLI/schema change. tail: {tail}"
            )

        if not out_dir.is_dir():
            raise MediaCrawlerScrapeError(
                f"MediaCrawler exited 0 but output dir {out_dir} does not exist. "
                "Output schema may have changed."
            )

        candidates = sorted(
            (p for p in out_dir.glob("search_contents_*.json") if p not in existing),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise MediaCrawlerScrapeError(
                f"MediaCrawler exited 0 but produced no new file in {out_dir}. "
                "Output schema may have changed."
            )
        return candidates[0]
