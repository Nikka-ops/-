from scripts.jobs.interview_link import match_posts_to_job
from scripts.jobs.models import JobPosting
from scripts.models import RawPost


def test_match_posts_to_job_by_company_and_title():
    job = JobPosting(
        source="job_pro",
        source_id="1",
        url="https://jobs.example/1",
        title="AI应用开发工程师",
        company="字节跳动",
    )
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/abc",
        post_type="text",
        raw_text="字节跳动 AI应用开发 一面 项目拷打",
        company="字节跳动",
    )
    matched = match_posts_to_job(job, [post])
    assert len(matched) == 1


def test_match_posts_to_job_different_company():
    job = JobPosting(
        source="job_pro",
        source_id="2",
        url="https://jobs.example/2",
        title="后端开发",
        company="腾讯",
    )
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/def",
        post_type="text",
        raw_text="字节跳动 后端 面经",
        company="字节跳动",
    )
    assert match_posts_to_job(job, [post]) == []
