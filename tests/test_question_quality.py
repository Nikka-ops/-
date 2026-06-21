from scripts.corpus.quality import is_interview_question, is_narrative_commentary


def test_rejects_advice_narrative_not_question():
    text = (
        "建议想要应聘新点算法岗的牛友好好背背基础八股，感觉一面不怎么拷打项目，"
        "中心还是在八股吧。问的是数据预处理流程，模型部署步骤之类的八股，"
        "不过我光顾着背改进原因了没背八股"
    )
    assert is_narrative_commentary(text)
    assert not is_interview_question(text)


def test_accepts_real_question_with_question_mark():
    assert is_interview_question("分支覆盖率是怎么统计的？原理有没有了解过？")
    assert is_interview_question("RAG 检索链路怎么设计？")


def test_accepts_short_ask_prompt():
    assert is_interview_question("介绍一下你做的项目和技术亮点")
