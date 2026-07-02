"""Boss直聘 — 通过 Chrome CDP 复用浏览器登录态（无需手抄 Cookie）。"""
from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlencode

from scripts.config import boss_cdp_port
from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.cdp_client import CdpError, cdp_port_open, evaluate_json, open_zhipin_page
from scripts.jobs.connectors.boss_zhipin import (
    apply_boss_detail,
    parse_boss_joblist,
    _resolve_city_code,
)

_JOBLIST_API = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
_DETAIL_API = "https://www.zhipin.com/wapi/zpgeek/job/detail.json"


def _build_joblist_js(query: str, city_code: str, page_size: int, page: int = 1) -> str:
    params = urlencode(
        {
            "scene": "1",
            "query": query,
            "city": city_code,
            "page": str(page),
            "pageSize": str(min(page_size, 30)),
        }
    )
    url = f"{_JOBLIST_API}?{params}"
    # 在 zhipin.com 页面上下文中同步请求，自动带上 Cookie / zp_stoken
    return (
        "(function(){"
        "try {"
        f"var xhr=new XMLHttpRequest();xhr.open('GET','{url}',false);"
        "xhr.setRequestHeader('Accept','application/json');"
        "xhr.send();"
        "return JSON.parse(xhr.responseText||'{}');"
        "} catch(e) { return {code:-1,message:String(e)}; }"
        "})()"
    )


def _build_detail_js(security_id: str) -> str:
    params = urlencode({"securityId": security_id})
    url = f"{_DETAIL_API}?{params}"
    return (
        "(function(){"
        "try {"
        f"var xhr=new XMLHttpRequest();xhr.open('GET','{url}',false);"
        "xhr.setRequestHeader('Accept','application/json');"
        "xhr.send();"
        "return JSON.parse(xhr.responseText||'{}');"
        "} catch(e) { return {code:-1,message:String(e)}; }"
        "})()"
    )


class BossCdpConnector(JobConnector):
    name = "boss_cdp"
    label = "Boss直聘（CDP）"
    company = ""

    def __init__(
        self,
        *,
        port: int | None = None,
        with_details: bool = True,
        page_opener: Callable[[int], str] | None = None,
        evaluator: Callable[[str, str], dict] | None = None,
    ) -> None:
        self._port = port if port is not None else boss_cdp_port()
        self._with_details = with_details
        self._page_opener = page_opener or open_zhipin_page
        self._evaluator = evaluator

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        if not cdp_port_open(self._port):
            return JobSearchResult.degraded(
                self.name,
                f"Chrome CDP 未启动（端口 {self._port}）。"
                f"运行: bash scripts/tools/start-boss-cdp-chrome.sh",
            )

        city_code = _resolve_city_code(city)
        try:
            page_ws = self._page_opener(self._port)
        except CdpError as exc:
            return JobSearchResult.degraded(self.name, str(exc))
        except Exception as exc:  # noqa: BLE001
            return JobSearchResult.degraded(self.name, f"打开 Boss 页面失败: {exc}")

        all_jobs: list = []
        seen: set[str] = set()
        errors: list[str] = []

        for query in queries:
            if not query.strip():
                continue
            try:
                payload = self._fetch_joblist_pages(
                    page_ws, query.strip(), city_code, max_per_query,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query}: {exc}")
                continue

            code = payload.get("code")
            if code != 0:
                msg = str(payload.get("message") or payload.get("zpData") or code)
                if code == 37 or "异常" in msg or "登录" in msg:
                    return JobSearchResult.degraded(
                        self.name,
                        f"Boss 未登录或会话失效: {msg}。"
                        "请在 CDP Chrome 中打开 zhipin.com 并登录后重试。",
                    )
                errors.append(f"{query}: {msg}")
                continue

            for job in parse_boss_joblist(payload):
                job.source = "boss_cdp"
                fp = job.fingerprint()
                if fp in seen:
                    continue
                seen.add(fp)
                all_jobs.append(job)

        if self._with_details and all_jobs:
            self._enrich_descriptions(page_ws, all_jobs[: min(len(all_jobs), max_per_query * 2)])

        if not all_jobs and errors:
            return JobSearchResult.degraded(self.name, "; ".join(errors))
        return JobSearchResult.ok(all_jobs, f"{len(all_jobs)} jobs via CDP")

    def _fetch_joblist_pages(
        self,
        page_ws: str,
        query: str,
        city_code: str,
        limit: int,
        *,
        max_pages: int = 8,
    ) -> dict:
        merged_list: list = []
        last_payload: dict = {"code": -1, "message": "no pages"}
        for page in range(1, max_pages + 1):
            if len(merged_list) >= limit:
                break
            page_size = min(30, limit - len(merged_list))
            payload = self._fetch_via_cdp(page_ws, query, city_code, page_size, page=page)
            last_payload = payload
            code = payload.get("code")
            if code != 0:
                return payload
            zp = payload.get("zpData") or {}
            batch = zp.get("jobList") or []
            merged_list.extend(batch)
            if not batch or not zp.get("hasMore"):
                break
        if last_payload.get("code") != 0:
            return last_payload
        return {
            "code": 0,
            "message": last_payload.get("message"),
            "zpData": {"jobList": merged_list[:limit], "hasMore": False},
        }

    def _fetch_via_cdp(
        self,
        page_ws: str,
        query: str,
        city_code: str,
        limit: int,
        *,
        page: int = 1,
    ) -> dict:
        js = _build_joblist_js(query, city_code, limit, page=page)
        if self._evaluator:
            data = self._evaluator(page_ws, js)
            if not isinstance(data, dict):
                raise CdpError("evaluator 必须返回 dict")
            return data
        data = evaluate_json(page_ws, js)
        if not isinstance(data, dict):
            raise CdpError(f"Boss API 返回非 JSON 对象: {json.dumps(data)[:200]}")
        return data

    def _enrich_descriptions(self, page_ws: str, jobs: list) -> None:
        for job in jobs:
            if job.description:
                continue
            security_id = str((job.extra or {}).get("security_id") or "").strip()
            if not security_id:
                continue
            try:
                payload = self._fetch_detail_via_cdp(page_ws, security_id)
                apply_boss_detail(job, payload)
            except Exception:  # noqa: BLE001
                continue

    def _fetch_detail_via_cdp(self, page_ws: str, security_id: str) -> dict:
        js = _build_detail_js(security_id)
        if self._evaluator:
            data = self._evaluator(page_ws, js)
            if not isinstance(data, dict):
                raise CdpError("evaluator 必须返回 dict")
            return data
        data = evaluate_json(page_ws, js)
        if not isinstance(data, dict):
            raise CdpError(f"Boss detail API 返回非 JSON 对象: {json.dumps(data)[:200]}")
        return data
