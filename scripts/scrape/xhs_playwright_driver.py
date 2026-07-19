"""Best-effort Xiaohongshu scraping through a logged-in Chrome CDP session."""
from __future__ import annotations

import importlib.util
import json
import random
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from scripts.config import cache_dir, xhs_cdp_port
from scripts.scrape.spider_xhs_normalize import note_from_search_item


class PlaywrightXHSScrapeError(RuntimeError):
    pass


class XHSCaptchaError(PlaywrightXHSScrapeError):
    """Raised when XHS shows a human-verification challenge (rate/behaviour based)."""


def _has_captcha(page) -> bool:
    """Detect XHS's verify/slider challenge so the run stops instead of hammering."""
    try:
        return bool(page.evaluate(
            """
            () => {
              if (/verify|captcha|security/i.test(location.href)) return true;
              const sel = '.captcha, .verify-wrapper, [class*="captcha"], [class*="verify"], .red-captcha';
              if (document.querySelector(sel)) return true;
              const t = document.body ? document.body.innerText : '';
              return /滑动|拖动|完成验证|安全验证|请完成|验证码/.test(t) && t.length < 400;
            }
            """
        ))
    except Exception:  # noqa: BLE001
        return False


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _browser_output_dir() -> Path:
    return cache_dir() / "xhs"


def _search_url(keyword: str) -> str:
    return f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}&source=web_explore_feed"


def _extract_dom_cards(page) -> list[dict]:
    rows = page.evaluate(
        """
        () => {
          const nodes = Array.from(document.querySelectorAll('a[href*="/explore/"]'));
          const seen = new Set();
          const out = [];
          for (const a of nodes) {
            const href = a.href || '';
            const match = href.match(/\\/explore\\/([^?#/]+)/);
            if (!match) continue;
            const noteId = match[1];
            if (!noteId || seen.has(noteId)) continue;
            seen.add(noteId);
            const card = a.closest('section, article, div') || a.parentElement;
            const text = (card?.innerText || a.innerText || '').trim();
            const title = (a.innerText || '').trim().split('\\n')[0] || text.split('\\n')[0] || '';
            const imageList = Array.from(card?.querySelectorAll('img') || [])
              .map((img) => img.currentSrc || img.src || '')
              .filter(Boolean)
              .slice(0, 9);
            out.push({
              note_id: noteId,
              note_url: href,
              title,
              desc: text.slice(0, 500),
              time: 0,
              image_list: imageList,
              tags: [],
            });
          }
          return out.slice(0, 60);
        }
        """
    )
    return rows if isinstance(rows, list) else []


class PlaywrightXHSDriver:
    def __init__(self, cdp_port: int | None = None):
        self.cdp_port = cdp_port or xhs_cdp_port()

    @property
    def output_dir(self) -> Path:
        return _browser_output_dir()

    def scrape_xhs(
        self,
        keywords: list[str],
        *,
        require_num_per_keyword: int | None = None,
        pause_seconds: float = 2.0,
        fetch_detail: bool = False,
    ) -> Path:
        del fetch_detail  # Browser mode only captures search-stage note cards.
        if not playwright_available():
            raise PlaywrightXHSScrapeError(
                "未安装 Playwright。请执行 pip install playwright 并安装浏览器依赖。"
            )

        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned:
            raise ValueError("keywords must be non-empty")

        per_kw = require_num_per_keyword or 20
        merged: list[dict] = []
        seen_ids: set[str] = set()

        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.cdp_port}")
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                try:
                    for i, keyword in enumerate(cleaned):
                        if i and pause_seconds > 0:
                            # Human-like jitter: never a fixed cadence. A real user
                            # doesn't search on a metronome — randomising the gap is
                            # what keeps the behavioural (captcha) detector quiet.
                            time.sleep(pause_seconds + random.uniform(0, pause_seconds))

                        captured: list[dict] = []

                        def _on_response(resp) -> None:
                            # XHS moved the search API to so.xiaohongshu.com and v2;
                            # match on the stable "search/notes" path so both the old
                            # (edith/v1) and new (so/v2) endpoints are captured.
                            if "search/notes" not in resp.url:
                                return
                            try:
                                payload = resp.json()
                            except Exception:  # noqa: BLE001
                                return
                            items = ((payload.get("data") or {}) if isinstance(payload, dict) else {}).get("items") or []
                            if not isinstance(items, list):
                                return
                            for item in items:
                                if not isinstance(item, dict):
                                    continue
                                note = note_from_search_item(item)
                                if note:
                                    captured.append(note)

                        page.on("response", _on_response)
                        page.goto(_search_url(keyword), wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(4000)
                        # Stop the whole run the moment a captcha appears — hammering
                        # more keywords only deepens the block. Keep what we have.
                        if _has_captcha(page):
                            page.remove_listener("response", _on_response)
                            if merged:
                                break
                            raise XHSCaptchaError(
                                "小红书弹出人机验证（频率触发）。请在专用 Chrome 手动完成验证，"
                                "并降低抓取频次/单次词数后重试。"
                            )
                        for _ in range(3):
                            page.mouse.wheel(0, random.randint(2200, 3400))
                            page.wait_for_timeout(random.randint(1500, 2600))
                        page.remove_listener("response", _on_response)

                        notes = captured[:per_kw]
                        if not notes:
                            notes = _extract_dom_cards(page)[:per_kw]
                        for note in notes:
                            note_id = str(note.get("note_id") or "").strip()
                            if not note_id or note_id in seen_ids:
                                continue
                            seen_ids.add(note_id)
                            merged.append(note)
                finally:
                    page.close()
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            raise PlaywrightXHSScrapeError(
                f"Playwright 浏览器抓取失败：{exc}. 请先启动并登录 XHS CDP Chrome（9233）。"
            ) from exc
        except OSError as exc:
            raise PlaywrightXHSScrapeError(
                f"无法连接 XHS CDP Chrome（9233）：{exc}. 请先运行 start-xhs-cdp-chrome.sh。"
            ) from exc

        if not merged:
            raise PlaywrightXHSScrapeError(
                "Playwright 未抓到任何搜索结果。请确认专用 Chrome 已登录，并手动搜索一次目标关键词。"
            )

        out_dir = self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"xhs_export_playwright_{date.today().isoformat()}.json"
        existing: list[dict] = []
        if out_path.is_file():
            try:
                raw = json.loads(out_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    existing = raw
            except (OSError, json.JSONDecodeError):
                pass
        by_id = {str(n.get("note_id") or ""): n for n in existing if n.get("note_id")}
        for note in merged:
            by_id[str(note.get("note_id") or "")] = note
        out_path.write_text(
            json.dumps(list(by_id.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out_path
