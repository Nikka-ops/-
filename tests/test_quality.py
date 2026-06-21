from scripts.corpus.quality import clean_question_text, filter_by_companies, is_low_quality_question
from scripts.models import Question


def test_clean_question_strips_xhs_marker():
    assert clean_question_text("[一R] attention 公式？") == "attention 公式？"


def test_is_low_quality_narrative():
    assert is_low_quality_question("首先声明楼主是菜鸡这是一段很长的感受没有问号")


def test_filter_by_companies_keeps_unlabeled():
    qs = [
        Question("通用题？", company_tags=[]),
        Question("字节题？", company_tags=["字节跳动"]),
        Question("腾讯题？", company_tags=["腾讯"]),
    ]
    out = filter_by_companies(qs, ["字节跳动"])
    assert len(out) == 2
    texts = {q.text for q in out}
    assert "字节题？" in texts
    assert "通用题？" in texts
