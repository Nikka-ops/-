"""Consolidated: test_jobs_role_filter.py, test_jobs_api.py, test_job_connectors.py, test_jobs_service.py, test_job_enrich.py, test_job_posted_at.py, test_boss_activity.py, test_boss_cdp_listen.py, test_boss_cdp_connector.py"""


# --- test_jobs_role_filter.py ---

from scripts.jobs.models import JobPosting
from scripts.jobs.queries import build_job_search_queries
from scripts.jobs.role_filter import filter_jobs_by_focus_roles, job_matches_focus_roles


def test_job_queries_exclude_mianjing():
    qs = build_job_search_queries("data", companies=["字节跳动"])
    assert qs
    assert all("面经" not in q for q in qs)
    assert any("数据开发" in q for q in qs)


def test_job_role_filter_uses_tags():
    job = JobPosting(
        source="boss_zhipin",
        source_id="1",
        url="u",
        title="研发工程师",
        company="字节跳动",
        description="",
        tags=["Spark", "Hive", "数仓"],
    )
    assert job_matches_focus_roles(job, ["data"]) is True


def test_keeps_data_and_agent_titles():
    jobs = [
        JobPosting(source="job_pro:bytedance", source_id="1", url="u1", title="数据开发工程师", company="字节跳动"),
        JobPosting(source="boss_zhipin", source_id="2", url="u2", title="Agent 应用开发", company="美团"),
        JobPosting(source="job_pro:tencent", source_id="3", url="u3", title="Java 后端开发", company="腾讯"),
    ]
    kept, meta = filter_jobs_by_focus_roles(jobs, ["data", "ai_app"])
    titles = {j.title for j in kept}
    assert "数据开发工程师" in titles
    assert "Agent 应用开发" in titles
    assert "Java 后端开发" not in titles
    assert meta["dropped"] == 1


def test_agent_keyword_in_description():
    job = JobPosting(
        source="boss_zhipin",
        source_id="x",
        url="u",
        title="研发工程师",
        company="阿里",
        description="负责 RAG 与 LangChain Agent 编排",
    )
    assert job_matches_focus_roles(job, ["ai_app"])

# --- test_jobs_api.py ---

from scripts.api.server import handle_request


def test_api_jobs_sources():
    status, payload = handle_request("GET", "/api/jobs/sources")
    assert status == 200
    sources = payload["sources"]
    assert any(s["id"] == "boss_zhipin" for s in sources)
    assert any(s["id"] == "bytedance" for s in sources)


def test_api_jobs_fetch_with_bytedance_only():
    status, payload = handle_request(
        "POST",
        "/api/jobs/fetch",
        {
            "role_id": "ai_app",
            "sources": ["bytedance"],
            "max_per_query": 2,
            "no_boss": True,
        },
    )
    assert status == 200
    assert payload["job_count"] >= 1
    assert "bytedance" in payload["sources"]
    assert payload["sources"]["bytedance"]["status"] == "ok"

# --- test_job_connectors.py ---

from pathlib import Path

import json

from scripts.jobs.connectors.boss_zhipin import BossZhipinConnector, parse_boss_joblist
from scripts.jobs.connectors.bytedance import ByteDanceConnector, parse_bytedance_search

FIXTURE_BOSS = Path(__file__).parent / "fixtures" / "boss_joblist.json"
FIXTURE_BD = Path(__file__).parent / "fixtures" / "bytedance_jobs.json"


def test_parse_boss_joblist():
    payload = json.loads(FIXTURE_BOSS.read_text(encoding="utf-8"))
    jobs = parse_boss_joblist(payload)
    assert len(jobs) == 2
    assert jobs[0].source == "boss_zhipin"
    assert jobs[0].title == "AI 应用开发工程师"
    assert jobs[0].company == "字节跳动"
    assert jobs[0].salary == "30-50K·15薪"
    assert "RAG" in jobs[0].tags
    assert "abc123encrypt" in jobs[0].url


def test_boss_connector_with_injected_fetcher():
    payload = json.loads(FIXTURE_BOSS.read_text(encoding="utf-8"))

    def fetcher(url, params):
        return payload

    conn = BossZhipinConnector(cookie="dummy=1", fetcher=fetcher)
    result = conn.search(["AI 应用"], max_per_query=10)
    assert result.status == "ok"
    assert len(result.jobs) == 2


def test_boss_connector_degrades_without_cookie(monkeypatch):
    import scripts.jobs.cdp_client as cdp

    monkeypatch.setattr(cdp, "cdp_port_open", lambda port: False)
    conn = BossZhipinConnector(cookie="")
    result = conn.search(["后端"])
    assert result.status == "degraded"
    assert "Cookie" in result.message or "CDP" in result.message


def test_parse_bytedance_search():
    payload = json.loads(FIXTURE_BD.read_text(encoding="utf-8"))
    jobs = parse_bytedance_search(payload)
    assert len(jobs) == 1
    assert jobs[0].company == "字节跳动"
    assert "RAG" in jobs[0].description
    assert jobs[0].city == "北京"
    assert jobs[0].posted_at == "2025-12-02"


def test_bytedance_connector_with_injected_fetcher():
    payload = json.loads(FIXTURE_BD.read_text(encoding="utf-8"))

    def fetcher(url, body):
        return payload

    conn = ByteDanceConnector(fetcher=fetcher)
    # bypass csrf by injecting session that won't be used
    conn._ensure_csrf = lambda session: "token"  # type: ignore[method-assign]
    result = conn.search(["AI"], max_per_query=5)
    assert result.status == "ok"
    assert len(result.jobs) == 1
    assert result.jobs[0].title.startswith("AI应用开发")

# --- test_jobs_service.py ---

from unittest.mock import patch

from pathlib import Path

from scripts.jobs.connectors.registry import resolve_connector_ids
from scripts.jobs.models import JobPosting
from scripts.jobs.service import JobFetchConfig, fetch_jobs
from scripts.jobs.store import jobs_snapshot_slug, load_snapshot


def test_resolve_connector_ids_for_company():
    ids = resolve_connector_ids(companies=["字节跳动"], include_aggregators=True)
    assert "boss_zhipin" in ids
    assert "job_pro" in ids


def test_jobs_snapshot_marks_new(tmp_path: Path):
    config = JobFetchConfig(
        role="AI 应用开发",
        companies=["字节跳动"],
        sources=["bytedance"],
        include_aggregators=False,
        cache_dir=str(tmp_path),
    )
    slug = jobs_snapshot_slug("AI 应用开发", ["字节跳动"], [])
    job = JobPosting(
        source="bytedance",
        source_id="1",
        url="https://jobs.bytedance.com/experienced/position/1/detail",
        title="AI 工程师",
        company="字节跳动",
        description="JD text",
    )

    from scripts.jobs.base import JobSearchResult

    def fake_search(self, queries, *, city=None, max_per_query=20):
        return JobSearchResult.ok([job])

    with patch("scripts.jobs.connectors.bytedance.ByteDanceConnector.search", fake_search):
        first = fetch_jobs(config, tmp_path)
    assert first.job_count == 1
    assert first.new_count == 1

    with patch("scripts.jobs.connectors.bytedance.ByteDanceConnector.search", fake_search):
        second = fetch_jobs(config, tmp_path)
    assert second.job_count == 1
    assert second.new_count == 0

    bundle = load_snapshot(tmp_path, slug)
    assert bundle is not None
    assert bundle["meta"]["job_count"] == 1

# --- test_job_enrich.py ---

from unittest.mock import patch

from scripts.jobs.enrich import enrich_job_pro_description
from scripts.jobs.models import JobPosting


def test_enrich_job_pro_description():
    job = JobPosting(
        source="job_pro:tencent",
        source_id="1216462959547938816",
        url="https://join.qq.com/post_detail.html?postid=1216462959547938816",
        title="AI-HR培训生",
        company="腾讯",
        extra={"job_pro_key": "tencent"},
    )
    detail = {
        "description": "岗位描述段落",
        "requirements": "任职要求段落",
    }

    with patch(
        "scripts.jobs.connectors.job_pro.JobProConnector._fetch_detail",
        return_value=detail,
    ):
        ok = enrich_job_pro_description(job)
    assert ok
    assert "岗位描述段落" in job.description
    assert "任职要求" in job.description

# --- test_job_posted_at.py ---

from datetime import date

from scripts.jobs.models import JobPosting
from scripts.jobs.posted_at import (
    coerce_posted_at,
    filter_official_jobs_by_recency,
    parse_posted_at_from_payload,
    sort_jobs_by_posted_at,
)


def test_coerce_posted_at_epoch_ms():
    assert coerce_posted_at(1764664441763) == "2025-12-02"


def test_parse_posted_at_from_payload():
    assert parse_posted_at_from_payload({"publish_time": 1764664441763}) == "2025-12-02"


def test_filter_official_jobs_by_recency():
    ref = date(2026, 6, 19)
    jobs = [
        JobPosting("job_pro:tencent", "1", "u", "t", "腾讯", posted_at="2026-05-01"),
        JobPosting("job_pro:bytedance", "2", "u", "t", "字节跳动", posted_at="2025-01-01"),
        JobPosting("job_pro:meituan", "3", "u", "t", "美团"),
        JobPosting("boss_zhipin", "4", "u", "t", "美团"),
    ]
    kept, meta = filter_official_jobs_by_recency(jobs, window_days=60, today=ref)
    assert len(kept) == 2
    assert kept[0].source == "job_pro:tencent"
    assert kept[1].source == "boss_zhipin"
    assert meta["official_dropped_old"] == 1
    assert meta["official_dropped_no_date"] == 1


def test_sort_jobs_by_posted_at():
    jobs = [
        JobPosting("job_pro:tencent", "1", "u", "a", "腾讯", posted_at="2026-04-01"),
        JobPosting("job_pro:tencent", "2", "u", "b", "腾讯", posted_at="2026-06-01"),
    ]
    sorted_jobs = sort_jobs_by_posted_at(jobs)
    assert [j.title for j in sorted_jobs] == ["b", "a"]

# --- test_boss_activity.py ---

from scripts.jobs.boss_activity import (
    apply_boss_activity_to_job,
    boss_activity_score,
    filter_jobs_by_boss_activity,
    parse_boss_activity_from_detail,
)
from scripts.jobs.models import JobPosting


def test_parse_boss_activity_from_detail():
    payload = {
        "code": 0,
        "zpData": {
            "bossInfo": {
                "activeTimeDesc": "近一周内活跃",
                "replyLevelName": "今日回复10+",
                "bossOnline": False,
                "name": "李女士",
            },
            "jobInfo": {"jobStatusDesc": "招聘中"},
        },
    }
    meta = parse_boss_activity_from_detail(payload)
    assert meta["boss_active_desc"] == "近一周内活跃"
    assert meta["boss_reply_hint"] == "今日回复10+"
    assert "近一周" in str(meta["boss_activity_text"])


def test_boss_activity_score():
    assert boss_activity_score("近一周内活跃") == 3
    assert boss_activity_score("今日回复10+") == 4
    assert boss_activity_score("刚刚活跃") == 5
    assert boss_activity_score("") == 0


def test_filter_jobs_by_boss_activity():
    active = JobPosting(
        "boss_zhipin",
        "1",
        "u",
        "t",
        "c",
        extra={"boss_activity_fetched": True, "boss_active_desc": "近一周内活跃", "boss_activity_score": 3},
    )
    stale = JobPosting(
        "boss_zhipin",
        "2",
        "u",
        "t",
        "c",
        extra={"boss_activity_fetched": True, "boss_active_desc": "本月活跃", "boss_activity_score": 2},
    )
    unknown = JobPosting("boss_zhipin", "3", "u", "t", "c", extra={})
    kept, meta = filter_jobs_by_boss_activity([active, stale, unknown], min_level="week")
    assert [j.source_id for j in kept] == ["1"]
    assert meta["dropped_inactive"] == 1
    assert meta["dropped_no_detail"] == 1


def test_apply_boss_activity_to_job():
    job = JobPosting("boss_zhipin", "x", "u", "t", "c")
    apply_boss_activity_to_job(
        job,
        {
            "code": 0,
            "zpData": {"bossInfo": {"activeTimeDesc": "今日活跃"}},
        },
    )
    assert job.extra["boss_active_desc"] == "今日活跃"
    assert job.extra["boss_activity_score"] == 4

# --- test_boss_cdp_listen.py ---

import json
from pathlib import Path

from scripts.jobs.cdp_listen import _payload_dedupe_key, jobs_from_joblist_payload


def test_payload_dedupe_key():
    payload = {
        "code": 0,
        "zpData": {"jobList": [{"encryptJobId": "abc123"}, {"encryptJobId": "def456"}]},
    }
    assert _payload_dedupe_key(payload) == "2:abc123|def456"


def test_jobs_from_fixture_payload():
    payload = json.loads(
        Path("tests/fixtures/boss_joblist.json").read_text(encoding="utf-8")
    )
    jobs = jobs_from_joblist_payload(payload)
    assert len(jobs) == 2
    assert jobs[0].title == "AI 应用开发工程师"
    assert jobs[0].company == "字节跳动"

# --- test_boss_cdp_connector.py ---

import json

from scripts.jobs.connectors.boss_cdp import BossCdpConnector, _build_detail_js, _build_joblist_js
from scripts.jobs.connectors.boss_zhipin import parse_boss_detail, parse_boss_joblist

FIXTURE = {
    "code": 0,
    "zpData": {
        "jobList": [
            {
                "encryptJobId": "cdp123",
                "jobName": "AI 应用开发",
                "brandName": "某科技公司",
                "cityName": "上海",
                "salaryDesc": "20-35K",
                "jobExperience": "1-3年",
                "jobDegree": "本科",
                "securityId": "sec-abc",
            }
        ]
    }
}

DETAIL_FIXTURE = {
    "code": 0,
    "zpData": {
        "jobInfo": {
            "postDescription": "负责 AI 应用落地与 RAG 系统建设。",
        }
    },
}


def test_build_joblist_js_contains_query():
    js = _build_joblist_js("AI应用", "101020100", 10)
    assert "AI" in js or "AI%E" in js or "AI应用" in js
    assert "101020100" in js


def test_build_detail_js_contains_security_id():
    js = _build_detail_js("sec-abc")
    assert "sec-abc" in js or "sec%2Dabc" in js
    assert "detail.json" in js


def test_parse_boss_detail():
    assert "RAG" in parse_boss_detail(DETAIL_FIXTURE)


def test_boss_cdp_connector_with_mock_evaluator(monkeypatch):
    payload = FIXTURE

    def evaluator(page_ws, js):
        if "joblist.json" in js:
            return payload
        if "detail.json" in js:
            return DETAIL_FIXTURE
        return {}

    def fake_opener(port):
        return "ws://fake-page"

    monkeypatch.setattr("scripts.jobs.connectors.boss_cdp.cdp_port_open", lambda p: True)
    conn = BossCdpConnector(port=9222, page_opener=fake_opener, evaluator=evaluator)
    result = conn.search(["AI应用"], max_per_query=5)
    assert result.status == "ok"
    assert len(result.jobs) == 1
    assert result.jobs[0].source == "boss_cdp"
    assert result.jobs[0].title == "AI 应用开发"
    assert not result.jobs[0].description


def test_parse_boss_joblist_still_works():
    jobs = parse_boss_joblist(FIXTURE)
    assert len(jobs) == 1
    assert jobs[0].salary == "20-35K"
