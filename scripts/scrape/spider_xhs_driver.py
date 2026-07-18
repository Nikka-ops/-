"""Drive Spider_XHS for keyword search → notes JSON export."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

_HTTP_461_HINT = (
    "小红书返回 HTTP 461（登录失效或风控）。"
    "请在专用 Chrome（CDP 9233）打开 xiaohongshu.com，手动搜一次确认有结果后再重试。"
    "若本地已有导出 JSON，可用 full_scrape --skip-xhs 直接入库。"
)


_MAX_CONSEC_SEARCH_FAIL = 6   # empty/failed keyword searches in a row → abort
_MAX_CONSEC_DETAIL_FAIL = 8   # failed note-detail fetches in a row → abort
_AUTH_ERROR_MARKERS = ("登录", "已过期", "风控", "461", "unauthorized", "forbidden", "验证")


def _looks_like_auth_error(msg: object) -> bool:
    s = str(msg or "").lower()
    return any(m in s for m in _AUTH_ERROR_MARKERS)


class SpiderXHSNotInstalledError(FileNotFoundError):
    pass


class SpiderXHSScrapeError(RuntimeError):
    pass


def _detect_home() -> Path:
    env = os.environ.get("SPIDER_XHS_HOME")
    return Path(env).expanduser() if env else Path.home() / ".spider_xhs"


def _patch_upstream_msg(home: Path) -> None:
    api = home / "apis" / "xhs_pc_apis.py"
    if not api.is_file():
        return
    needle = 'success, msg = res_json["success"], res_json["msg"]'
    repl = 'success, msg = res_json["success"], res_json.get("msg", "")'
    try:
        text = api.read_text(encoding="utf-8")
    except OSError:
        return
    if needle in text and repl not in text:
        api.write_text(text.replace(needle, repl), encoding="utf-8")


@contextmanager
def _spider_xhs_runtime(home: Path):
    home = home.expanduser().resolve()
    if not (home / "apis" / "xhs_pc_apis.py").is_file():
        raise SpiderXHSNotInstalledError(
            f"Spider_XHS not found at {home}. "
            "Run: git clone https://github.com/cv-cat/Spider_XHS.git ~/.spider_xhs "
            "&& cd ~/.spider_xhs && npm install"
        )
    if not (home / "node_modules").is_dir():
        subprocess.run(["npm", "install", "--silent"], cwd=str(home), check=True, timeout=300)
    _patch_upstream_msg(home)

    prev_cwd = os.getcwd()
    home_str = str(home)
    in_path = home_str in sys.path
    if not in_path:
        sys.path.insert(0, home_str)
    os.chdir(home_str)
    try:
        yield home
    finally:
        os.chdir(prev_cwd)
        if not in_path and sys.path and sys.path[0] == home_str:
            sys.path.pop(0)


def resolve_xhs_cookies() -> str:
    from scripts.config import xhs_cdp_enabled, xhs_cdp_port, xhs_cookies_str
    from scripts.jobs.cdp_client import cdp_extract_cookies_string, cdp_port_open

    cookies = xhs_cookies_str()
    if cookies:
        return cookies
    if xhs_cdp_enabled() and cdp_port_open(xhs_cdp_port()):
        live = cdp_extract_cookies_string(xhs_cdp_port())
        if live:
            return live
    return ""


def _probe_search(cookies: str) -> tuple[int, int]:
    """Return (http_status, item_count) for a test keyword search."""
    from xhs_utils.xhs_util import generate_request_params, generate_x_rap_param, generate_search_id
    import requests

    api = "/api/sns/web/v1/search/notes"
    data = {
        "keyword": "面经",
        "page": 1,
        "page_size": 5,
        "search_id": generate_search_id(),
        "sort": "general",
        "note_type": 0,
        "ext_flags": [],
        "filters": [
            {"tags": ["general"], "type": "sort_type"},
            {"tags": ["不限"], "type": "filter_note_type"},
            {"tags": ["不限"], "type": "filter_note_time"},
            {"tags": ["不限"], "type": "filter_note_range"},
            {"tags": ["不限"], "type": "filter_pos_distance"},
        ],
        "geo": "",
        "image_formats": ["jpg", "webp", "avif"],
    }
    headers, ck, body = generate_request_params(cookies, api, data, "POST")
    headers["x-rap-param"] = generate_x_rap_param(api, data)
    resp = requests.post(
        "https://edith.xiaohongshu.com" + api,
        headers=headers,
        data=body.encode("utf-8"),
        cookies=ck,
        timeout=30,
    )
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        payload = {}
    items = ((payload.get("data") or {}) if isinstance(payload, dict) else {}).get("items") or []
    return resp.status_code, len(items)


class SpiderXHSDriver:
    def __init__(self, home: Path | None = None):
        self.home = (home or _detect_home()).expanduser()

    @property
    def output_dir(self) -> Path:
        return self.home / "data" / "xhs" / "json"

    def scrape_xhs(
        self,
        keywords: list[str],
        *,
        require_num_per_keyword: int | None = None,
        sort_type_choice: int = 0,
        pause_seconds: float = 2.0,
        fetch_detail: bool = True,
    ) -> Path:
        from scripts.config import xhs_crawler_max_notes, xhs_max_keywords_per_run
        from scripts.scrape.spider_xhs_normalize import note_from_handled, note_from_search_item

        cleaned = [k.strip() for k in keywords if k and k.strip()][: xhs_max_keywords_per_run()]
        if not cleaned:
            raise ValueError("keywords must be non-empty")

        cookies = resolve_xhs_cookies()
        if not cookies or "web_session=" not in cookies:
            raise SpiderXHSScrapeError(
                "小红书 Cookie 未配置。请在专用 Chrome（CDP 9233）登录，或设置 XHS_COOKIES。"
            )

        per_kw = require_num_per_keyword or max(10, min(30, xhs_crawler_max_notes()))
        merged: list[dict] = []
        seen_ids: set[str] = set()

        with _spider_xhs_runtime(self.home):
            from apis.xhs_pc_apis import XHS_Apis
            from xhs_utils.data_util import handle_note_info

            status, n = _probe_search(cookies)
            if status == 461:
                raise SpiderXHSScrapeError(_HTTP_461_HINT)
            if n == 0 and status != 200:
                raise SpiderXHSScrapeError(f"小红书搜索不可用（HTTP {status}）。")

            api = XHS_Apis()
            # Circuit breaker: a session that expires or gets risk-controlled
            # mid-run makes every subsequent call fail. Abort early instead of
            # grinding through all keywords (the old behaviour logged ~90 errors).
            consec_search_fail = 0
            consec_detail_fail = 0
            for i, keyword in enumerate(cleaned):
                if i and pause_seconds > 0:
                    time.sleep(pause_seconds)
                ok, msg, items = api.search_some_note(
                    keyword, per_kw, cookies, sort_type_choice=sort_type_choice
                )
                if _looks_like_auth_error(msg):
                    raise SpiderXHSScrapeError(f"登录失效/风控（{msg}）。{_HTTP_461_HINT}")
                if not ok or not items:
                    consec_search_fail += 1
                    if consec_search_fail >= _MAX_CONSEC_SEARCH_FAIL and not merged:
                        raise SpiderXHSScrapeError(
                            f"连续 {consec_search_fail} 个关键词无结果，疑似登录失效/风控。{_HTTP_461_HINT}"
                        )
                    continue
                consec_search_fail = 0
                for item in items:
                    if item.get("model_type") != "note":
                        continue
                    note_id = str(item.get("id") or "").strip()
                    if not note_id or note_id in seen_ids:
                        continue
                    note_dict = None
                    if fetch_detail:
                        xsec = str(item.get("xsec_token") or "").strip()
                        url = f"https://www.xiaohongshu.com/explore/{note_id}"
                        if xsec:
                            url += f"?xsec_token={xsec}"
                        ok_d, msg_d, detail = api.get_note_info(url, cookies)
                        if _looks_like_auth_error(msg_d):
                            raise SpiderXHSScrapeError(f"登录失效/风控（{msg_d}）。{_HTTP_461_HINT}")
                        if ok_d and detail and detail.get("data", {}).get("items"):
                            raw = detail["data"]["items"][0]
                            raw["url"] = url
                            note_dict = note_from_handled(handle_note_info(raw))
                            consec_detail_fail = 0
                        else:
                            consec_detail_fail += 1
                            if consec_detail_fail >= _MAX_CONSEC_DETAIL_FAIL and not merged:
                                raise SpiderXHSScrapeError(
                                    f"连续 {consec_detail_fail} 篇笔记详情抓取失败，疑似登录失效/风控。{_HTTP_461_HINT}"
                                )
                    else:
                        note_dict = note_from_search_item(item)
                    if note_dict:
                        seen_ids.add(note_id)
                        merged.append(note_dict)

        if not merged:
            raise SpiderXHSScrapeError(
                f"未抓到笔记（{len(cleaned)} 个关键词均无结果）。{_HTTP_461_HINT}"
            )

        out_dir = self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"search_contents_{date.today().isoformat()}.json"
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
