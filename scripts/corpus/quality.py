"""Filter and normalize question bank rows."""
from __future__ import annotations

import re

from scripts.models import Question

_EMOJI_MARKER = re.compile(r"^\[[^\]]+\]\s*")
_NARRATIVE = re.compile(
    r"^(?:"
    r"首先声明|楼主|本文|分享|更新|备注|"
    r"个人经验|时间线|感受|总结|建议|奉劝|友情提示|"
    r"个人觉得|我感觉|说实话|总的来说|总体来说"
    r")",
    re.I,
)
_ADVICE_CHATTER = re.compile(
    r"(?:"
    r"牛友|友友们|好好背|光顾着背|背背基础|面经分享|"
    r"不怎么拷打|中心还是在|仅供参考|经验之谈"
    r")",
    re.I,
)
_ASK_HINT = re.compile(
    r"(?:"
    r"什么|哪些|怎样|为啥|是否|能不能|可不可以|"
    r"怎么|如何|为什么|为何|区别|差异|原理|实现|设计|优化|排查|"
    r"介绍|说说|讲讲|描述|解释|手撕|手写"
    r")",
    re.I,
)


def clean_question_text(text: str) -> str:
    text = _EMOJI_MARKER.sub("", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_narrative_commentary(text: str) -> bool:
    cleaned = clean_question_text(text)
    if _NARRATIVE.match(cleaned):
        return True
    if _ADVICE_CHATTER.search(cleaned):
        return True
    # 长段叙述且无明确问句标点 → 面经感想/建议，不是面试题
    if len(cleaned) > 72 and not re.search(r"[？?]", cleaned):
        if cleaned.endswith(("吗", "嘛")):
            return False
        return True
    if cleaned.count("，") >= 4 and not re.search(r"[？?]", cleaned):
        return True
    return False


def is_interview_question(text: str) -> bool:
    """True only for lines that look like an actual interview question/prompt."""
    cleaned = clean_question_text(text)
    if len(cleaned) < 8:
        return False
    if is_narrative_commentary(cleaned):
        return False
    if _NARRATIVE.match(cleaned):
        return False
    if "？" in cleaned or "?" in cleaned:
        return True
    if cleaned.endswith("吗") or cleaned.endswith("嘛"):
        return True
    if len(cleaned) <= 120 and _ASK_HINT.search(cleaned):
        return True
    return False


def is_low_quality_question(text: str) -> bool:
    return not is_interview_question(text)


def filter_question_dicts(rows: list[dict]) -> list[dict]:
    return [q for q in rows if is_interview_question(q.get("text") or "")]


def filter_questions(questions: list[Question]) -> list[Question]:
    out: list[Question] = []
    for q in questions:
        text = clean_question_text(q.text)
        if is_low_quality_question(text):
            continue
        if text != q.text:
            q = Question(
                text=text,
                source_refs=q.source_refs,
                freq=q.freq,
                latest_posted_at=q.latest_posted_at,
                role_tags=q.role_tags,
                company_tags=q.company_tags,
                topic=q.topic,
                modality_origin=q.modality_origin,
            )
        out.append(q)
    return out


def filter_by_companies(questions: list[Question], companies: list[str]) -> list[Question]:
    if not companies:
        return questions
    targets = {c.strip() for c in companies if c.strip()}
    if not targets:
        return questions
    filtered: list[Question] = []
    for q in questions:
        if not q.company_tags:
            filtered.append(q)
            continue
        if any(c in targets for c in q.company_tags):
            filtered.append(q)
    return filtered
