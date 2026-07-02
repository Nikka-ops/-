"""Boss直聘 — 基于 DrissionPage 网络监听，规避风控。

核心原理：用 DrissionPage 驱动真实 Chrome，监听 joblist.json 接口，
拦截浏览器原生发出的请求响应，而非注入 XHR，绕过 Boss 的异常检测。
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.connectors.boss_zhipin import (
    apply_boss_detail,
    parse_boss_joblist,
    _resolve_city_code,
)

_JOBLIST_KEYWORD = "joblist.json"
_DETAIL_KEYWORD  = "job/detail.json"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def _make_search_url(query: str, city_code: str, page: int = 1, page_size: int = 30) -> str:
    from urllib.parse import urlencode
    params = urlencode({
        "scene": "1",
        "query": query,
        "city": city_code,
        "page": str(page),
        "pageSize": str(min(page_size, 30)),
    })
    return f"https://www.zhipin.com/web/geek/jobs?{params}"


def _make_detail_url(security_id: str) -> str:
    from urllib.parse import urlencode
    return f"https://www.zhipin.com/wapi/zpgeek/job/detail.json?{urlencode({'securityId': security_id})}"


class BossDrissionConnector(JobConnector):
    """使用 DrissionPage 监听网络接口，无风控注入。"""

    name = "boss_drission"
    label = "Boss直聘（DrissionPage）"
    company = ""

    def __init__(
        self,
        *,
        with_details: bool = True,
        headless: bool = False,
        page_wait: float = 3.0,
        listen_timeout: float = 10.0,
    ) -> None:
        self._with_details = with_details
        self._headless = headless
        self._page_wait = page_wait
        self._listen_timeout = listen_timeout
        self._page: Any = None

    # ------------------------------------------------------------------
    def _get_page(self):
        """懒初始化 DrissionPage，优先接管已开启的 CDP Chrome（9222）。"""
        if self._page is not None:
            return self._page
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions
        except ImportError as e:
            raise RuntimeError("请先安装 DrissionPage: pip install DrissionPage") from e

        # 尝试连接已登录的 CDP Chrome（端口 9222）
        from scripts.jobs.cdp_client import cdp_port_open
        cdp_port = 9222
        if cdp_port_open(cdp_port):
            try:
                opts = ChromiumOptions()
                opts.set_address(f"127.0.0.1:{cdp_port}")
                self._page = ChromiumPage(addr_or_opts=opts)
                return self._page
            except Exception:  # noqa: BLE001
                pass  # fallback to new instance

        # 无已有 Chrome，启动新实例
        opts = ChromiumOptions()
        opts.set_argument("--disable-blink-features=AutomationControlled")
        opts.set_argument(f"--user-agent={random.choice(_USER_AGENTS)}")
        if self._headless:
            opts.headless()
        self._page = ChromiumPage(addr_or_opts=opts)
        return self._page

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.quit()
            except Exception:  # noqa: BLE001
                pass
            self._page = None

    # ------------------------------------------------------------------
    def _fetch_joblist(self, query: str, city_code: str, max_jobs: int) -> list[dict]:
        page = self._get_page()
        collected: list[dict] = []
        pg = 1

        while len(collected) < max_jobs:
            url = _make_search_url(query, city_code, page=pg, page_size=30)

            # 开始监听 joblist 接口
            page.listen.start(_JOBLIST_KEYWORD)
            page.get(url)

            try:
                resp = page.listen.wait(timeout=self._listen_timeout)
            except Exception:  # noqa: BLE001
                break
            finally:
                page.listen.stop()

            if resp is None:
                break

            try:
                body = resp.response.body
                if isinstance(body, (bytes, bytearray)):
                    body = body.decode("utf-8", errors="replace")
                if isinstance(body, str):
                    data = json.loads(body)
                elif isinstance(body, dict):
                    data = body
                else:
                    break
            except Exception:  # noqa: BLE001
                break

            if not isinstance(data, dict) or data.get("code") != 0:
                break

            zp = data.get("zpData") or {}
            batch = zp.get("jobList") or []
            collected.extend(batch)

            if not batch or not zp.get("hasMore") or len(collected) >= max_jobs:
                break

            pg += 1
            time.sleep(random.uniform(1.5, 2.5))

        return collected[:max_jobs]

    def _fetch_detail(self, security_id: str) -> dict:
        page = self._get_page()
        url = _make_detail_url(security_id)
        page.listen.start(_DETAIL_KEYWORD)
        page.get(url)
        try:
            resp = page.listen.wait(timeout=self._listen_timeout)
        except Exception:  # noqa: BLE001
            return {}
        finally:
            page.listen.stop()
        if resp is None:
            return {}
        try:
            body = resp.response.body
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8", errors="replace")
            if isinstance(body, str):
                return json.loads(body)
            if isinstance(body, dict):
                return body
            return {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------------
    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 30,
    ) -> JobSearchResult:
        city_code = _resolve_city_code(city)
        all_jobs = []
        seen: set[str] = set()

        try:
            for query in queries:
                if not query.strip():
                    continue
                raw_list = self._fetch_joblist(query.strip(), city_code, max_per_query)
                fake_payload = {"code": 0, "zpData": {"jobList": raw_list}}
                for job in parse_boss_joblist(fake_payload):
                        job.source = "boss_drission"
                        fp = job.fingerprint()
                        if fp in seen:
                            continue
                        seen.add(fp)
                        all_jobs.append(job)
                time.sleep(random.uniform(1.0, 2.0))

            if self._with_details and all_jobs:
                self._enrich(all_jobs[:min(len(all_jobs), max_per_query * 3)])

        except Exception as exc:  # noqa: BLE001
            if not all_jobs:
                return JobSearchResult.degraded(self.name, str(exc))

        return JobSearchResult.ok(all_jobs, f"{len(all_jobs)} jobs via DrissionPage")

    def _enrich(self, jobs: list) -> None:
        for job in jobs:
            if job.description:
                continue
            security_id = str((job.extra or {}).get("security_id") or "").strip()
            if not security_id:
                continue
            try:
                payload = self._fetch_detail(security_id)
                apply_boss_detail(job, payload)
            except Exception:  # noqa: BLE001
                continue
            time.sleep(random.uniform(0.8, 1.5))
