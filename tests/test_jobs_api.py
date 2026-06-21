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
