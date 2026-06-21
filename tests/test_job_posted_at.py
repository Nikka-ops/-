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
