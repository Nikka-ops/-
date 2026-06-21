from scripts.corpus.classify import classify_search_queries, extract_company_role, infer_company_from_text


def test_infer_company_from_body_text():
    assert infer_company_from_text("今天面试字节跳动大模型岗位") == "字节跳动"
    assert infer_company_from_text("美团 Agent 方向技术面") == "美团"


def test_extract_company_from_desc_when_title_missing():
    company, role = extract_company_role(title="面经分享", desc="腾讯后端开发一面总结")
    assert company == "腾讯"


def test_extract_company_role_from_nowcoder_style_title():
    company, role = extract_company_role(title="字节 AI 应用开发 一面面经")
    assert company == "字节跳动"
    assert role == "AI 应用开发"


def test_extract_company_role_from_xhs_title():
    company, role = extract_company_role(title="腾讯 产品经理 实习 面经")
    assert company == "腾讯"
    assert "产品" in role


def test_extract_company_role_from_tags():
    company, role = extract_company_role(
        title="某厂面经分享",
        tags=["#字节", "AI应用开发"],
    )
    assert company == "字节跳动"
    assert role == "AI 应用开发"


def test_extract_company_role_from_bracketed_nowcoder_title():
    company, role = extract_company_role(title="【面试真题】字节 AI 应用岗")
    assert company == "字节跳动"
    assert role == "AI 应用开发"


def test_extract_company_role_from_meituan_agent_direction():
    company, role = extract_company_role(title="【面试真题】美团Agent 方向面经整理")
    assert company == "美团"
    assert role in {"AI 应用开发", "AI/Agent 应用开发"}


def test_extract_returns_none_for_unlabeled_title():
    company, role = extract_company_role(title="无日期帖", desc="今天天气不错，随便聊聊。")
    assert company is None
    assert role is None


def test_extract_rejects_year_as_company():
    company, role = extract_company_role(title="【面经分享】2026 Java 后端开发 面经")
    assert company is None
    assert role is not None
    assert "Java" in role or "后端" in role


def test_classify_search_queries_builds_role_and_company_batches():
    queries = classify_search_queries(
        roles=["AI 应用开发", "产品经理"],
        companies=["字节跳动", "腾讯"],
    )
    assert "AI 应用开发 面经" in queries
    assert "字节跳动 AI 应用开发 面经" in queries
    assert "腾讯 产品经理 实习 面经" in queries
    assert len(queries) == len(set(queries))
