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
