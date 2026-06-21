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
