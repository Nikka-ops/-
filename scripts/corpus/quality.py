"""Question text cleanup + offline filter (agent cluster handles filtering when API key set)."""
from __future__ import annotations

import re

from scripts.models import Question

_EMOJI = re.compile(r"^\[[^\]]+\]\s*")
_OFFLINE_DROP = re.compile(
    r"自我介绍|介绍(?:一下)?自己|优缺点|职业规划|离职|期望薪资|到岗|反问|哪里人|三年规划|五年规划",
    re.I,
)
_NARRATIVE_DROP = re.compile(
    r"(?:面经|行情|岗位|招聘|offer|内推|实习|秋招|春招).{0,20}(?:分享|推荐|总结|经验|建议|吐槽|感受|感想)|"
    r"(?:最近|目前|现在|今年).{0,20}(?:行情|hc|市场|竞争|内卷)|"
    r"(?:希望|祝|感谢|谢谢|加油|冲冲冲)",
    re.I,
)
# Verbs/patterns that signal an interview question even without "?"
_ASK_VERB = re.compile(
    r"讲讲|说说|介绍(?:一下)?(?!自己)|描述|解释|手撕|实现|设计|优化|排查|"
    r"怎么|如何|为什么|为何|区别|差异|原理",
    re.IGNORECASE,
)


def clean_question_text(text: str) -> str:
    return re.sub(r"\s+", " ", _EMOJI.sub("", text.strip())).strip()


def is_interview_question(text: str) -> bool:
    t = clean_question_text(text)
    if len(t) < 4 or len(t) > 300:
        return False
    if _OFFLINE_DROP.search(t):
        return False
    # Narrative commentary (long sentence with no question marker)
    if len(t) > 80 and not re.search(r"[？?]", t) and not t.endswith(("吗", "嘛")) and _NARRATIVE_DROP.search(t):
        return False
    # Accept: has explicit question marker
    if re.search(r"[？?]", t) or t.endswith(("吗", "嘛")):
        return True
    # Accept: imperative interview question patterns (no "?" but question-like verb)
    if _ASK_VERB.search(t):
        return True
    # Accept: introduce + project
    if "介绍" in t and "项目" in t:
        return True
    return False


def is_narrative_commentary(text: str) -> bool:
    t = clean_question_text(text)
    return len(t) > 72 and not re.search(r"[？?]", t)


def is_low_quality_question(text: str) -> bool:
    return not is_interview_question(text)


def filter_question_dicts(rows: list[dict]) -> list[dict]:
    return [q for q in rows if is_interview_question(q.get("text") or "")]


def filter_questions(questions: list[Question]) -> list[Question]:
    out: list[Question] = []
    for q in questions:
        text = clean_question_text(q.text)
        if not text or not is_interview_question(text):
            continue
        if text != q.text:
            q = Question(**{**q.to_dict(), "text": text})
        out.append(q)
    return out


def filter_by_companies(questions: list[Question], companies: list[str]) -> list[Question]:
    if not companies:
        return questions
    targets = {c.strip() for c in companies if c.strip()}
    return [q for q in questions if not q.company_tags or any(c in targets for c in q.company_tags)]
