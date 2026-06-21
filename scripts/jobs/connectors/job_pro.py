"""job-pro CLI 适配器 — 复用开源 https://github.com/HA7CH/job-pro 。"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence

from scripts.jobs.base import JobConnector, JobSearchResult
from scripts.jobs.models import JobPosting

# InterviewRadar canonical 公司名 → job-pro adapter key
COMPANY_TO_JOB_PRO_KEY: dict[str, str] = {
    "字节跳动": "bytedance",
    "腾讯": "tencent",
    "阿里巴巴": "alibaba",
    "美团": "meituan",
    "百度": "baidu",
    "网易": "netease",
    "滴滴": "didi",
    "京东": "jd",
    "拼多多": "pdd",
    "华为": "huawei",
    "快手": "kuaishou",
    "小米": "xiaomi",
    "哔哩哔哩": "bilibili",
    "小红书": "xiaohongshu",
    "商汤": "sensetime",
    "科大讯飞": "iflytek",
    "oppo": "oppo",
    "vivo": "vivo",
    "比亚迪": "byd",
    "蔚来": "nio",
    "理想": "liauto",
    "小鹏": "xpeng",
    "蚂蚁集团": "ant",
    "携程": "ctrip",
    "顺丰": "sf",
    "微博": "weibo",
}

JOB_PRO_KEY_TO_COMPANY: dict[str, str] = {v: k for k, v in COMPANY_TO_JOB_PRO_KEY.items()}


def _default_command() -> list[str]:
    env_bin = shutil.which("job-pro")
    if env_bin:
        return [env_bin]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "job-pro@1.1.0"]
    return ["npx", "-y", "job-pro@1.1.0"]


def _run_job_pro(
    argv: Sequence[str],
    *,
    runner: Callable[[list[str]], str] | None = None,
    timeout: int = 120,
) -> dict:
    base = _default_command()
    cmd = list(base) + list(argv)
    if runner is not None:
        raw = runner(cmd)
    else:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(tail or f"job-pro exited {proc.returncode}")
        raw = proc.stdout
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("job-pro compact output must be a JSON object")
    return data


def _position_to_job(
    company_key: str,
    pos: dict,
    *,
    detail: dict | None = None,
) -> JobPosting | None:
    post_id = str(pos.get("post_id") or pos.get("id") or "").strip()
    title = str(pos.get("title") or "").strip()
    if not post_id or not title:
        return None
    company = JOB_PRO_KEY_TO_COMPANY.get(company_key, company_key)
    url = str(pos.get("apply_url") or pos.get("url") or "").strip()
    if not url:
        url = f"job-pro:{company_key}:{post_id}"
    city_raw = pos.get("work_cities")
    if isinstance(city_raw, list):
        city = " ".join(str(c) for c in city_raw if c) or None
    else:
        city = str(city_raw or "").strip() or None

    description = ""
    if detail:
        desc = str(detail.get("description") or "").strip()
        req = str(detail.get("requirements") or detail.get("requirement") or "").strip()
        if desc and req:
            description = f"{desc}\n\n任职要求:\n{req}"
        else:
            description = desc or req
    tags: list[str] = []
    for key in ("project", "recruit_label", "direction", "bgs"):
        val = pos.get(key) or (detail or {}).get(key)
        if val:
            tags.append(str(val))

    from scripts.jobs.posted_at import parse_posted_at_from_payload

    posted_at = parse_posted_at_from_payload(pos)
    if detail and not posted_at:
        posted_at = parse_posted_at_from_payload(detail)

    return JobPosting(
        source=f"job_pro:{company_key}",
        source_id=post_id,
        url=url,
        title=title,
        company=company,
        description=description,
        role=title,
        city=city,
        posted_at=posted_at,
        status="open",
        tags=tags,
        extra={
            "job_pro_key": company_key,
            "apply_url": url,
        },
    )


class JobProConnector(JobConnector):
    """Shell out to job-pro CLI; no duplicate per-company API logic in InterviewRadar."""

    name = "job_pro"
    label = "job-pro（开源 50 家大厂）"
    company = ""

    def __init__(
        self,
        *,
        company_keys: list[str] | None = None,
        scope: str = "social",
        with_details: bool = True,
        runner: Callable[[list[str]], str] | None = None,
        command: list[str] | None = None,
    ) -> None:
        self._company_keys = company_keys
        self._scope = scope
        self._with_details = with_details
        self._runner = runner
        self._command = command

    def search(
        self,
        queries: list[str],
        *,
        city: str | None = None,
        max_per_query: int = 20,
    ) -> JobSearchResult:
        del city  # job-pro uses work city filters internally per adapter
        keys = self._company_keys or []
        if not keys:
            return JobSearchResult.degraded(self.name, "未指定 job-pro 公司 key")

        terms = self._search_terms(queries)
        per_term = max(max_per_query, 30)
        per_company = min(per_term, 50)

        try:
            all_jobs: list[JobPosting] = []
            seen_fp: set[str] = set()
            company_errors: list[str] = []
            for term in terms:
                if len(keys) == 1:
                    batches = [(keys[0], self._search_one_safe(keys[0], term, per_term, company_errors))]
                else:
                    batches = [
                        (key, self._search_one_safe(key, term, per_company, company_errors))
                        for key in keys
                    ]
                for _key, batch in batches:
                    for job in batch:
                        fp = job.fingerprint()
                        if fp in seen_fp:
                            continue
                        seen_fp.add(fp)
                        all_jobs.append(job)
        except FileNotFoundError:
            return JobSearchResult.degraded(
                self.name,
                "未找到 npx/job-pro。请安装 Node.js 18+ 或 npm i -g job-pro",
            )
        except Exception as exc:  # noqa: BLE001
            return JobSearchResult.degraded(self.name, str(exc))

        msg = f"{len(all_jobs)} jobs via job-pro"
        if company_errors:
            msg += f" ({len(company_errors)} 公司失败)"
        return JobSearchResult.ok(all_jobs, msg)

    def _search_one_safe(
        self,
        company_key: str,
        keyword: str,
        limit: int,
        errors: list[str],
    ) -> list[JobPosting]:
        try:
            return self._search_one(company_key, keyword, limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{company_key}:{exc}")
            return []

    def _search_terms(self, queries: list[str]) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for q in queries:
            text = q.strip()
            if text and text not in seen:
                seen.add(text)
                terms.append(text)
        if not terms:
            terms.append("开发")
        return terms[:25]

    def _search_one(self, company_key: str, keyword: str, limit: int) -> list[JobPosting]:
        argv = [
            company_key,
            "search",
            keyword,
            "--scope",
            self._scope,
            "--page-size",
            str(min(limit, 100)),
            "--compact",
        ]
        data = _run_job_pro(argv, runner=self._runner)
        if not data.get("ok"):
            raise RuntimeError(str(data.get("message") or data))
        positions = data.get("positions") or []
        jobs: list[JobPosting] = []
        for pos in positions[:limit]:
            job = _position_to_job(company_key, pos, detail=None)
            if job:
                jobs.append(job)
        return jobs

    def _search_find(self, keys: list[str], keyword: str, limit: int) -> list[JobPosting]:
        argv = [
            "find",
            keyword,
            "--companies",
            ",".join(keys),
            "--limit",
            str(min(limit, 100)),
            "--compact",
        ]
        data = _run_job_pro(argv, runner=self._runner)
        if not data.get("ok"):
            raise RuntimeError(str(data.get("message") or data))
        jobs: list[JobPosting] = []
        for block in data.get("results") or []:
            if not isinstance(block, dict) or not block.get("ok"):
                continue
            company_key = str(block.get("company") or "")
            for pos in block.get("positions") or []:
                job = _position_to_job(company_key, pos, detail=None)
                if job:
                    jobs.append(job)
        return jobs[:limit]

    def _fetch_detail(self, company_key: str, post_id: str) -> dict | None:
        if not post_id:
            return None
        argv = [company_key, "detail", post_id, "--compact"]
        if self._scope:
            argv.extend(["--scope", self._scope])
        try:
            data = _run_job_pro(argv, runner=self._runner, timeout=60)
        except Exception:  # noqa: BLE001
            return None
        if not data.get("ok"):
            return None
        return data


def resolve_job_pro_keys(companies: list[str]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for name in companies:
        key = COMPANY_TO_JOB_PRO_KEY.get(name.strip())
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys
