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
