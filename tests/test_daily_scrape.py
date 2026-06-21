from datetime import date, timedelta

from scripts.corpus.company_catalog import all_preset_companies, resolve_company_list
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.scrape_state import (
    append_rolling_nowcoder_posts,
    filter_new_nowcoder_posts,
    load_scrape_state,
    pick_nowcoder_query_batch,
    pick_xhs_keyword_batch,
    save_scrape_state,
)
from scripts.models import RawPost


def test_resolve_company_list_all():
    names = resolve_company_list("all")
    assert len(names) == len(all_preset_companies())
    assert "字节跳动" in names


def test_xhs_keyword_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    keywords = ["a", "b", "c", "d", "e"]
    state = load_scrape_state()
    b1 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b1 == ["a", "b"]
    b2 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b2 == ["c", "d"]
    b3 = pick_xhs_keyword_batch(keywords, state, per_day=2)
    assert b3 == ["e", "a"]


def test_nowcoder_query_stale_after_day():
    state = {"query_last_run": {"q1": (date.today() - timedelta(days=2)).isoformat()}}
    batch = pick_nowcoder_query_batch(["q1", "q2"], state, per_day=5, min_days_between=1)
    assert "q1" in batch


def test_filter_and_append_rolling_nowcoder(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    state = load_scrape_state()
    p1 = RawPost(source="nowcoder", url="https://www.nowcoder.com/feed/main/detail/u1", post_type="text", raw_text="a")
    p2 = RawPost(source="nowcoder", url="https://www.nowcoder.com/feed/main/detail/u2", post_type="text", raw_text="b")
    new_only = filter_new_nowcoder_posts([p1, p2], state)
    assert len(new_only) == 2
    again = filter_new_nowcoder_posts([p1], state)
    assert len(again) == 0
    assert append_rolling_nowcoder_posts(new_only) == 2
    assert append_rolling_nowcoder_posts([p1]) == 0


def test_xhs_keywords_for_ai_app_all_companies():
    keys = xhs_keywords_for_role("ai_app", all_preset_companies())
    assert len(keys) >= 100
    assert all("面经" in k for k in keys)
