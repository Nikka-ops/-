import json
from pathlib import Path

from scripts.jobs.connectors.job_pro import JobProConnector, _position_to_job

FIXTURE_FIND = Path(__file__).parent / "fixtures" / "job_pro_find.json"


def test_position_to_job():
    pos = {
        "post_id": "1",
        "title": "后端开发",
        "work_cities": "北京",
        "apply_url": "https://example.com/j/1",
        "project": "技术",
        "recruit_label": "正式",
    }
    detail = {
        "description": "做后端服务",
        "requirements": "熟悉 Java",
    }
    job = _position_to_job("tencent", pos, detail=detail)
    assert job is not None
    assert job.company == "腾讯"
    assert job.source == "job_pro:tencent"
    assert "做后端服务" in job.description
    assert "熟悉 Java" in job.description


def test_job_pro_connector_multi_company_with_injected_runner():
    payload = json.loads(FIXTURE_FIND.read_text(encoding="utf-8"))
    block_by_key = {b["company"]: b for b in payload["results"]}

    def runner(cmd):
        assert "search" in cmd
        key = next((p for p in cmd if p in block_by_key), None)
        block = block_by_key.get(key or "")
        if not block:
            return json.dumps({"ok": False, "message": "missing"})
        return json.dumps(
            {
                "ok": True,
                "positions": block.get("positions") or [],
            }
        )

    conn = JobProConnector(
        company_keys=["tencent", "bytedance"],
        runner=runner,
    )
    result = conn.search(["AI应用"], max_per_query=10)
    assert result.status == "ok"
    assert len(result.jobs) == 2
    companies = {j.company for j in result.jobs}
    assert "腾讯" in companies
    assert "字节跳动" in companies
