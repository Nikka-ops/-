from scripts.corpus.company_normalize import infer_company_from_text_normalized, normalize_company_name


def test_taotian_to_alibaba():
    assert normalize_company_name("淘天") == "阿里巴巴"
    assert normalize_company_name("淘天集团") == "阿里巴巴"


def test_ant_and_qwen_to_alibaba():
    assert normalize_company_name("蚂蚁集团") == "阿里巴巴"
    assert normalize_company_name("通义千问") == "阿里巴巴"


def test_tencent_business_units():
    assert normalize_company_name("WXG") == "腾讯"
    assert normalize_company_name("csig") == "腾讯"


def test_bytedance_subsidiaries():
    assert normalize_company_name("TikTok") == "字节跳动"
    assert normalize_company_name("抖音") == "字节跳动"


def test_rejects_non_company_tags():
    assert normalize_company_name("AI") is None
    assert normalize_company_name("Ai") is None
    assert normalize_company_name("agent") is None
    assert normalize_company_name("27实习") is None
    assert normalize_company_name("双非") is None
    assert normalize_company_name("27") is None


def test_infer_from_text():
    assert infer_company_from_text_normalized("淘天 AI 应用开发一面") == "阿里巴巴"
    assert infer_company_from_text_normalized("WXG 后台开发二面") == "腾讯"
