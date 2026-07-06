"""Capture Boss joblist.json responses via Chrome CDP Network events."""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from scripts.jobs.cdp_client import (
    CdpError,
    CdpSession,
    cdp_port_open,
    evaluate_json,
    find_zhipin_page_ws,
    open_zhipin_page,
)
from scripts.jobs.connectors.boss_zhipin import parse_boss_joblist
from scripts.jobs.models import JobPosting
from scripts.config import boss_cdp_port

try:
    from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException
except ImportError:  # pragma: no cover
    WebSocketTimeoutException = Exception  # type: ignore[misc, assignment]
    WebSocketConnectionClosedException = ConnectionError  # type: ignore[misc, assignment]

_JOBLIST_MARK = "joblist"
_TRIGGER_SEARCH_JS = """
(function(){
  var input = document.querySelector('input[name="query"]') ||
    document.querySelector('.ipt-search') ||
    document.querySelector('input[placeholder*="搜索"]');
  var btn = document.querySelector('.search-btn') ||
    document.querySelector('.btn-search') ||
    document.querySelector('button[type="submit"]');
  if (btn) { btn.click(); return {ok:true, via:'click'}; }
  if (input) {
    input.dispatchEvent(new KeyboardEvent('keydown', {
      key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true
    }));
    return {ok:true, via:'enter'};
  }
  return {ok:false, reason:'no search control'};
})()
"""

_SCROLL_JS = """
(function(){
  var n = 0;
  document.querySelectorAll(
    '.job-list-box, .job-list, .scroll-content, [class*="job-list"], [class*="rec-job-list"]'
  ).forEach(function(el){
    if (el.scrollHeight > el.clientHeight + 20) {
      el.scrollTop = el.scrollHeight;
      n++;
    }
  });
  window.scrollTo(0, document.body.scrollHeight);
  window.dispatchEvent(new Event('scroll', {bubbles:true}));
  return {ok:true, scrolled_boxes:n};
})()
"""

# 交互模式：在页面里 hook fetch/XHR，短连接轮询，避免长 WebSocket 断连。
_INSTALL_JOBLIST_HOOK_JS = """
(function(){
  if (window.__bossJoblistHook) return {ok:true, already:true};
  window.__bossJoblistHook = true;
  window.__bossJoblistPayloads = window.__bossJoblistPayloads || [];
  function push(data) {
    try {
      if (data && data.code === 0) window.__bossJoblistPayloads.push(data);
    } catch (e) {}
  }
  var of = window.fetch;
  if (of) {
    window.fetch = function() {
      var p = of.apply(this, arguments);
      try {
        var u = String(arguments[0] && arguments[0].url || arguments[0] || '');
        if (u.indexOf('joblist') >= 0) {
          p.then(function(res) {
            res.clone().json().then(push).catch(function(){});
            return res;
          });
        }
      } catch (e) {}
      return p;
    };
  }
  var oOpen = XMLHttpRequest.prototype.open;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function() {
    this.__bossUrl = arguments[1];
    return oOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    var self = this;
    this.addEventListener('load', function() {
      if (String(self.__bossUrl || '').indexOf('joblist') >= 0) {
        try { push(JSON.parse(self.responseText)); } catch (e) {}
      }
    });
    return oSend.apply(this, arguments);
  };
  return {ok:true, mode:'hook'};
})()
"""

_READ_JOBLIST_PAYLOADS_JS = "JSON.stringify(window.__bossJoblistPayloads || [])"

_FETCH_JOBLIST_FROM_URL_JS = """
(function(maxPages){
  if (!location.hostname || location.hostname.indexOf('zhipin.com') < 0) {
    return {ok:false, error:'not on zhipin.com', payloads:[]};
  }
  var qs = new URLSearchParams(location.search);
  var filterKeys = [
    'query','city','jobType','scale','experience','degree','salary','industry',
    'stage','position','multiBusinessDistrict','multiSubway','district',
    'payType','partTime','subwayLineId','workPlace'
  ];
  var payloads = [];
  for (var page = 1; page <= maxPages; page++) {
    var params = new URLSearchParams();
    params.set('scene', '1');
    params.set('page', String(page));
    params.set('pageSize', '30');
    filterKeys.forEach(function(k){
      var v = qs.get(k);
      if (v !== null && v !== '') params.set(k, v);
    });
    if (!params.get('query')) params.set('query', qs.get('query') || '');
    var url = '/wapi/zpgeek/search/joblist.json?' + params.toString();
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.send();
      var data = JSON.parse(xhr.responseText || '{}');
      if (data.code !== 0) {
        return {
          ok:false, code:data.code, message:data.message || 'api error',
          payloads:payloads, page:page, url:location.href
        };
      }
      payloads.push(data);
      var hasMore = !!(data.zpData && data.zpData.hasMore);
      if (!hasMore) break;
    } catch (e) {
      return {ok:false, error:String(e), payloads:payloads, page:page, url:location.href};
    }
  }
  return {ok:true, payloads:payloads, count:payloads.length, url:location.href};
})(__MAX_PAGES__)
"""


class _PageNetworkSession:
    """CDP page session: RPC calls + queued domain events on one WebSocket."""

    def __init__(self, page_ws: str, *, recv_timeout: float = 1.0) -> None:
        self.page_ws = page_ws
        self._recv_timeout = recv_timeout
        self._session = CdpSession(page_ws, timeout=max(60.0, recv_timeout + 10))
        self._ws = self._session._ws  # noqa: SLF001
        self._ws.settimeout(recv_timeout)
        self._id = 0
        self._events: deque[dict[str, Any]] = deque()
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self._session.close()

    def _ingest(self, data: dict[str, Any]) -> None:
        if data.get("method"):
            self._events.append(data)

    def _recv(self) -> dict[str, Any]:
        if self.closed:
            raise CdpError("CDP 页面连接已关闭")
        try:
            raw = self._ws.recv()
        except WebSocketTimeoutException:
            return {}
        except WebSocketConnectionClosedException as exc:
            self.closed = True
            raise CdpError("CDP 页面连接断开（页面可能刷新或标签已关闭）") from exc
        if not raw:
            self.closed = True
            raise CdpError("CDP connection closed")
        data = json.loads(raw)
        if data.get("id") is not None and not data.get("method"):
            return data
        self._ingest(data)
        return data

    def enable_network(self) -> None:
        self.call("Network.enable")
        self.call("Runtime.enable")

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        msg_id = self._id
        self._ws.send(
            json.dumps({"id": msg_id, "method": method, "params": params or {}})
        )
        deadline = time.time() + 30.0
        while time.time() < deadline:
            data = self._recv()
            if not data:
                continue
            if data.get("id") == msg_id:
                if "error" in data:
                    raise CdpError(str(data["error"]))
                return data.get("result")
        raise CdpError(f"CDP timeout on {method}")

    def wait_for(self, method: str, *, timeout: float) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.closed:
                raise CdpError("CDP 页面连接已关闭")
            for i, ev in enumerate(self._events):
                if ev.get("method") == method:
                    del self._events[i]
                    return ev
            self._recv()
        return None


def _attach_page_session(page_ws: str) -> _PageNetworkSession:
    session = _PageNetworkSession(page_ws)
    session.enable_network()
    return session


def _reconnect_page_session(port: int, *, wait_sec: float = 2.0) -> _PageNetworkSession | None:
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        page_ws = find_zhipin_page_ws(port)
        if page_ws:
            time.sleep(0.5)
            try:
                return _attach_page_session(page_ws)
            except CdpError:
                time.sleep(0.4)
                continue
        time.sleep(0.3)
    return None


def _decode_body(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    body = result.get("body")
    if body is None:
        return None
    if result.get("base64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _payload_dedupe_key(payload: dict[str, Any]) -> str:
    jobs = (payload.get("zpData") or {}).get("jobList") or []
    ids = [
        str(item.get("encryptJobId") or item.get("jobId") or item.get("securityId") or "")
        for item in jobs[:5]
    ]
    return f"{len(jobs)}:" + "|".join(ids)


def capture_joblist_from_page_filters(
    *,
    port: int,
    max_pages: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch joblist using filter params from the current Boss page URL (short CDP calls)."""
    page_ws = find_zhipin_page_ws(port)
    if not page_ws:
        raise CdpError("未找到 Boss 页面标签，请先 bash scripts/tools/focus-boss-cdp-chrome.sh")

    js = _FETCH_JOBLIST_FROM_URL_JS.replace("__MAX_PAGES__", str(max(1, max_pages)))
    result = evaluate_json(page_ws, js)
    if not isinstance(result, dict):
        raise CdpError("Boss 页面返回异常")

    payloads = [
        item for item in (result.get("payloads") or [])
        if isinstance(item, dict) and item.get("code") == 0
    ]
    meta = {
        "capture_mode": "url_filters",
        "page_url": str(result.get("url") or ""),
        "max_pages": max_pages,
        "api_ok": bool(result.get("ok")),
        "api_message": str(result.get("message") or result.get("error") or ""),
    }
    if not result.get("ok") and not payloads:
        msg = meta["api_message"] or "joblist 拉取失败"
        raise CdpError(f"Boss joblist 拉取失败: {msg}")
    return payloads, meta


def capture_joblist_payloads_via_hook(
    *,
    port: int,
    listen_seconds: float = 30.0,
    poll_interval: float = 1.0,
    nudge_scroll: bool = True,
) -> list[dict[str, Any]]:
    """Poll page hook buffers; resilient to CDP page WebSocket drops."""
    deadline = time.time() + listen_seconds
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    hook_installed = False
    nudged = False

    while time.time() < deadline:
        page_ws = find_zhipin_page_ws(port)
        if not page_ws:
            time.sleep(poll_interval)
            continue
        try:
            if not hook_installed:
                evaluate_json(page_ws, _INSTALL_JOBLIST_HOOK_JS)
                hook_installed = True
                if nudge_scroll and not nudged:
                    try:
                        evaluate_json(page_ws, _SCROLL_JS)
                    except CdpError:
                        pass
                    nudged = True
            raw = evaluate_json(page_ws, _READ_JOBLIST_PAYLOADS_JS)
            items: list[Any]
            if isinstance(raw, str):
                items = json.loads(raw)
            elif isinstance(raw, list):
                items = raw
            else:
                items = []
            for item in items:
                if not isinstance(item, dict) or item.get("code") != 0:
                    continue
                key = _payload_dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                payloads.append(item)
        except CdpError:
            hook_installed = False
        time.sleep(poll_interval)

    return payloads


def capture_joblist_payloads(
    page_ws: str,
    *,
    port: int | None = None,
    listen_seconds: float = 20.0,
    trigger_search: bool = True,
    scroll_times: int = 0,
) -> list[dict[str, Any]]:
    """Listen for joblist responses on an already-open Boss page."""
    session = _attach_page_session(page_ws)
    payloads: list[dict[str, Any]] = []
    seen_req: set[str] = set()
    reconnects = 0

    def _maybe_reconnect() -> bool:
        nonlocal session, reconnects
        if port is None or reconnects >= 3:
            return False
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass
        new_session = _reconnect_page_session(port, wait_sec=5.0)
        if not new_session:
            return False
        session = new_session
        reconnects += 1
        return True

    try:
        time.sleep(0.3)

        if trigger_search:
            session.call(
                "Runtime.evaluate",
                {"expression": _TRIGGER_SEARCH_JS, "returnByValue": True},
            )

        deadline = time.time() + listen_seconds
        scroll_left = max(0, scroll_times)

        while time.time() < deadline:
            try:
                ev = session.wait_for("Network.responseReceived", timeout=1.0)
            except CdpError as exc:
                if "连接" not in str(exc):
                    raise
                if _maybe_reconnect():
                    continue
                if payloads:
                    break
                raise

            if not ev:
                if scroll_left > 0:
                    scroll_left -= 1
                    try:
                        session.call(
                            "Runtime.evaluate",
                            {"expression": _SCROLL_JS, "returnByValue": True},
                        )
                    except CdpError as exc:
                        if "连接" not in str(exc):
                            raise
                        if not _maybe_reconnect():
                            if payloads:
                                break
                            raise
                    time.sleep(1.2)
                continue

            resp = ev.get("params", {}).get("response", {})
            url = str(resp.get("url") or "")
            req_id = str(ev.get("params", {}).get("requestId") or "")
            if _JOBLIST_MARK not in url or not req_id or req_id in seen_req:
                continue
            seen_req.add(req_id)

            try:
                session.wait_for("Network.loadingFinished", timeout=8.0)
                body_result = session.call("Network.getResponseBody", {"requestId": req_id})
            except CdpError as exc:
                if "连接" in str(exc) and _maybe_reconnect():
                    continue
                continue
            parsed = _decode_body(body_result)
            if parsed and parsed.get("code") == 0:
                payloads.append(parsed)

    finally:
        session.close()

    return payloads


def capture_boss_jobs_via_listen(
    *,
    port: int | None = None,
    listen_seconds: float = 20.0,
    trigger_search: bool = True,
    scroll_times: int = 1,
    job_page_url: str = "https://www.zhipin.com/web/geek/job",
) -> tuple[list[JobPosting], dict[str, Any]]:
    port = boss_cdp_port() if port is None else port
    if not cdp_port_open(port):
        raise CdpError(
            f"Chrome CDP 未启动（端口 {port}）。运行: bash scripts/tools/start-boss-cdp-chrome.sh"
        )

    page_ws = open_zhipin_page(port, wait_sec=3.0)
    nav = _PageNetworkSession(page_ws)
    try:
        nav.call("Page.navigate", {"url": job_page_url})
    finally:
        nav.close()
    time.sleep(2.5)

    page_ws = open_zhipin_page(port, wait_sec=2.0)
    payloads = capture_joblist_payloads(
        page_ws,
        port=port,
        listen_seconds=listen_seconds,
        trigger_search=trigger_search,
        scroll_times=scroll_times,
    )

    jobs: list[JobPosting] = []
    seen: set[str] = set()
    for payload in payloads:
        for job in parse_boss_joblist(payload):
            fp = job.fingerprint()
            if fp in seen:
                continue
            seen.add(fp)
            jobs.append(job)

    meta = {
        "payload_count": len(payloads),
        "job_count": len(jobs),
        "port": port,
        "listen_seconds": listen_seconds,
        "trigger_search": trigger_search,
        "scroll_times": scroll_times,
    }
    return jobs, meta


def jobs_from_joblist_payload(payload: dict[str, Any]) -> list[JobPosting]:
    return parse_boss_joblist(payload)
