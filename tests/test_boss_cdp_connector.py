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
