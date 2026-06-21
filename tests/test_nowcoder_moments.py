from scripts.discover.nowcoder_moments import moment_to_raw_post, search_nowcoder_moments


def test_moment_to_raw_post():
    moment = {
        "id": 2859824,
        "uuid": "f054aef412104109a1dfa85e273e6faf",
        "title": "福州朴朴科技-算法工程师暑期实习-面经",
        "content": "1. 介绍项目\n2. 深度学习基础",
        "createdAt": 1780393247000,
    }
    post = moment_to_raw_post(moment)
    assert post is not None
    assert post.source == "nowcoder"
    assert "算法工程师" in post.raw_text
    assert "feed/main/detail" in post.url
    assert post.posted_at


def test_moment_from_content_data():
    from scripts.discover.nowcoder_moments import _moment_dict_from_payload, moment_to_raw_post

    payload = {
        "contentData": {
            "id": "888446465431830528",
            "uuid": "921b42b28fcf45d5bd63baa7489d048c",
            "title": "Ai Agent、ai应用开发面经面试题2",
            "content": "RAG 延迟优化与多路召回 …",
            "createTime": 1780393247000,
            "contentImageUrls": [],
        }
    }
    moment = _moment_dict_from_payload(payload)
    assert moment is not None
    post = moment_to_raw_post(moment)
    assert post is not None
    assert "RAG" in post.raw_text


def test_iter_search_payloads_skips_list_data():
    from scripts.discover.nowcoder_moments import _iter_search_payloads

    assert _iter_search_payloads({"data": [{"id": 1}]}) == [{"id": 1}]
    assert _iter_search_payloads({"data": {"momentData": {"id": 2}}}) == [{"momentData": {"id": 2}}]
    assert _iter_search_payloads({"data": None}) == []


def test_search_nowcoder_moments_live():
    posts, meta = search_nowcoder_moments(["算法工程师面经"], max_per_query=2, request_delay=0)
    assert meta["count"] == len(posts)
    assert len(posts) >= 1
    assert all(p.raw_text for p in posts)
