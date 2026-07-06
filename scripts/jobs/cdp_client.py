"""Minimal Chrome DevTools Protocol client (sync WebSocket)."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    from websocket import WebSocketTimeoutException, create_connection
except ImportError:  # pragma: no cover - optional until pip install
    create_connection = None  # type: ignore[misc, assignment]
    WebSocketTimeoutException = Exception  # type: ignore[misc, assignment]


class CdpError(RuntimeError):
    pass


class CdpSession:
    def __init__(self, ws_url: str, *, timeout: float = 30.0) -> None:
        if create_connection is None:
            raise CdpError("缺少 websocket-client，请 pip install -e '.[boss-cdp]'")
        self._ws = create_connection(ws_url, timeout=timeout)
        self._id = 0

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001
            pass

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        msg_id = self._id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        self._ws.send(json.dumps(payload))
        while True:
            try:
                raw = self._ws.recv()
            except WebSocketTimeoutException as exc:
                raise CdpError(f"CDP timeout on {method}") from exc
            if not raw:
                raise CdpError(f"CDP connection closed during {method}")
            data = json.loads(raw)
            if data.get("id") != msg_id:
                continue
            if "error" in data:
                raise CdpError(str(data["error"]))
            return data.get("result")


def cdp_list_targets(port: int) -> list[dict[str, Any]]:
    with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as resp:
        data = json.load(resp)
    return data if isinstance(data, list) else []


def cdp_browser_ws_url(port: int) -> str:
    with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as resp:
        data = json.load(resp)
    ws = data.get("webSocketDebuggerUrl")
    if not ws:
        raise CdpError("CDP 未返回 webSocketDebuggerUrl")
    return str(ws)


def cdp_port_open(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except (URLError, OSError, ValueError):
        return False


def cdp_extract_cookies_string(
    port: int,
    *,
    domains: tuple[str, ...] = ("xiaohongshu.com", "rednote.com"),
) -> str:
    """Read live cookie header string from CDP Chrome (XHS login window)."""
    if not cdp_port_open(port):
        return ""
    page_ws: str | None = None
    for target in cdp_list_targets(port):
        if target.get("type") != "page":
            continue
        url = str(target.get("url") or "")
        if not any(d in url for d in domains):
            continue
        ws = target.get("webSocketDebuggerUrl")
        if ws:
            page_ws = str(ws)
            break
    if not page_ws:
        return ""

    session = CdpSession(page_ws, timeout=15.0)
    try:
        session.call("Network.enable")
        seen: dict[str, str] = {}
        for url in (
            "https://www.xiaohongshu.com",
            "https://www.xiaohongshu.com/explore",
            "https://www.rednote.com",
        ):
            result = session.call("Network.getCookies", {"urls": [url]})
            cookies = result.get("cookies") if isinstance(result, dict) else []
            if not isinstance(cookies, list):
                continue
            for cookie in cookies:
                if not isinstance(cookie, dict):
                    continue
                name = str(cookie.get("name") or "").strip()
                value = str(cookie.get("value") or "").strip()
                domain = str(cookie.get("domain") or "")
                if not name or not value:
                    continue
                if any(d in domain for d in domains):
                    seen[name] = value
        return "; ".join(f"{k}={v}" for k, v in seen.items())
    except (CdpError, OSError, ValueError, json.JSONDecodeError):
        return ""
    finally:
        session.close()


def cdp_extract_web_session(port: int, *, domains: tuple[str, ...] = ("xiaohongshu.com", "rednote.com")) -> str:
    """Read live ``web_session`` from an existing CDP Chrome (XHS login window)."""
    for part in cdp_extract_cookies_string(port, domains=domains).split(";"):
        piece = part.strip()
        if piece.startswith("web_session="):
            return piece.split("=", 1)[1].strip()
    return ""


def find_zhipin_page_ws(port: int) -> str | None:
    pages: list[dict[str, Any]] = []
    for target in cdp_list_targets(port):
        if target.get("type") != "page":
            continue
        url = str(target.get("url") or "")
        if "zhipin.com" in url and target.get("webSocketDebuggerUrl"):
            pages.append(target)
    if not pages:
        return None

    def _score(target: dict[str, Any]) -> tuple[int, int]:
        url = str(target.get("url") or "")
        job_page = 1 if ("/job" in url or "/jobs" in url) else 0
        geek = 1 if "/geek/" in url else 0
        return (job_page + geek, len(url))

    best = max(pages, key=_score)
    return str(best["webSocketDebuggerUrl"])


def open_zhipin_page(port: int, *, wait_sec: float = 2.0) -> str:
    """Return WebSocket URL for a zhipin.com page (existing or newly opened)."""
    existing = find_zhipin_page_ws(port)
    if existing:
        return existing

    browser = CdpSession(cdp_browser_ws_url(port), timeout=15.0)
    try:
        browser.call("Target.createTarget", {"url": "https://www.zhipin.com/web/geek/jobs"})
    finally:
        browser.close()

    import time

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        ws = find_zhipin_page_ws(port)
        if ws:
            return ws
        time.sleep(0.25)

    targets = cdp_list_targets(port)
    for target in targets:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return str(target["webSocketDebuggerUrl"])
    raise CdpError("无法打开 Boss 直聘页面，请确认 Chrome CDP 已启动并已登录 zhipin.com")


def evaluate_json(page_ws: str, expression: str, *, timeout: float = 30.0) -> Any:
    session = CdpSession(page_ws, timeout=timeout)
    try:
        session.call("Runtime.enable")
        result = session.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
            },
        )
    finally:
        session.close()
    if not result:
        raise CdpError("Runtime.evaluate 无返回")
    if result.get("exceptionDetails"):
        raise CdpError(str(result["exceptionDetails"]))
    value = result.get("result", {}).get("value")
    if value is None:
        raise CdpError("页面脚本返回空值")
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return value
    raise CdpError(f"无法解析 CDP 返回: {type(value)}")
