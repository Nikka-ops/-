"""Extract normalized Question objects from scraped RawPost bodies."""
from __future__ import annotations

import re

from scripts.corpus.quality import clean_question_text, is_interview_question, is_low_quality_question
from scripts.models import Question, RawPost

_NUMBERED = re.compile(
    r"^\s*(?:"
    r"\d+[\.\)、．]"
    r"|[一二三四五六七八九十百]+[\、\.]"
    r"|\[\s*[一二三四五六七八九十\d]+\s*\]"
    r")\s*(.+)$"
)
_INLINE_NUMBERED_SPLIT = re.compile(
    r"(?<=[？?])\s*(?=\d+[\.\)、．]\s*)"
    r"|"
    r"(?:\s+)(?=\d+[\.\)、．]\s*)"
)
_OCR_PAGE = re.compile(r"\[图片 OCR 第\s*\d+\s*页\]\s*\n?", re.I)
_QUESTION_END = re.compile(r"[？?]\s*$")
_ASK_VERB = re.compile(
    r"(?:"
    r"问了|问到|考察|手撕|考一下|介绍一下|介绍|讲讲|说说|描述|解释|"
    r"怎么|如何|为什么|为何|区别|差异|原理|实现|设计|优化|排查"
    r")",
    re.IGNORECASE,
)
_SECTION_SKIP = re.compile(
    r"^(?:"
    r"一面|二面|三面|四面|五面|hr面|主管面|leader面|技术面|"
    r"感受|总结|反问|时长|背景|时间线|个人经验"
    r")[:：]?\s*$",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"^(?:"
    r"#.+#|"
    r"来源|参考|欢迎补充|如有侵权|转载请注明|"
    r"点赞|收藏|关注|蹲后续"
    r")",
    re.IGNORECASE,
)

_TOPIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("RAG", re.compile(r"rag|检索|召回|embedding|向量|rerank|切块|chunk", re.I)),
    ("Agent", re.compile(r"agent|react|plan.?execute|多智能体|工具调用|function.?call", re.I)),
    ("MCP/协议", re.compile(r"mcp|function.?calling|structured.?output|json.?mode", re.I)),
    ("LLM基础", re.compile(r"transformer|attention|qkv|rope|微调|sft|lora|rlhf|ppo|dpo", re.I)),
    ("手撕代码", re.compile(r"手撕|leetcode|力扣|coding|代码题|算法题", re.I)),
    ("项目深挖", re.compile(r"项目|实习|架构|系统设计|压测|qps|部署", re.I)),
    ("后端八股", re.compile(r"redis|mysql|kafka|tcp|线程|进程|锁|sql|jvm|spring", re.I)),
    ("产品/业务", re.compile(r"产品|业务|指标|实验|ab|用户|场景", re.I)),
]


def _clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[-*•·]\s*", "", line)
    line = re.sub(r"^\[.?\]\s*", "", line)
    return line.strip()


def _is_question_like(line: str) -> bool:
    if len(line) < 8 or len(line) > 280:
        return False
    if _NOISE.match(line):
        return False
    if _SECTION_SKIP.match(line):
        return False
    if _QUESTION_END.search(line):
        return True
    if _ASK_VERB.search(line) and (
        "?" in line
        or "？" in line
        or "怎么" in line
        or "如何" in line
        or "为什么" in line
        or "区别" in line
        or "原理" in line
        or "实现" in line
    ):
        return True
    if line.endswith("吗") or line.endswith("嘛"):
        return True
    return False


def infer_topic(text: str) -> str:
    for name, pattern in _TOPIC_RULES:
        if pattern.search(text):
            return name
    return "综合"


def _modality_from_post(post: RawPost) -> str:
    if post.extraction_quality.startswith("ocr"):
        return "ocr"
    if post.needs_vision_fallback:
        return "vision"
    return "text"


def _split_inline_numbered(line: str) -> list[str]:
    """One physical line may contain「…？ 18. … 19. …」— split before extracting."""
    parts = _INLINE_NUMBERED_SPLIT.split(line.strip())
    if len(parts) <= 1:
        return [line.strip()] if line.strip() else []
    return [p.strip() for p in parts if p.strip()]


def _post_body(post: RawPost) -> str:
    for field in (post.image_ocr_text, post.content_text, post.raw_text, post.locator_text):
        if field and str(field).strip():
            return str(field).strip()
    return ""


def _lines_from_post(post: RawPost) -> list[str]:
    body = _OCR_PAGE.sub("\n", _post_body(post))
    if not body:
        return []
    lines: list[str] = []
    for raw_line in body.splitlines():
        cleaned = _clean_line(raw_line)
        if not cleaned:
            continue
        for segment in _split_inline_numbered(cleaned):
            sub = _clean_line(segment)
            if sub:
                lines.append(sub)
    return lines


def extract_questions_from_post(post: RawPost) -> list[Question]:
    """Return one Question per extracted line (freq=1; caller merges via dedupe_and_rank)."""
    company_tags = [post.company] if post.company else []
    role_tags = [post.role] if post.role else []
    modality = _modality_from_post(post)
    out: list[Question] = []
    seen: set[str] = set()

    for line in _lines_from_post(post):
        candidate = line
        numbered = _NUMBERED.match(line)
        if numbered:
            candidate = numbered.group(1).strip()
            candidate = clean_question_text(candidate)
            if not is_interview_question(candidate):
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Question(
                    text=candidate,
                    source_refs=[post.url] if post.url else [],
                    freq=1,
                    latest_posted_at=post.posted_at,
                    role_tags=list(role_tags),
                    company_tags=list(company_tags),
                    topic=infer_topic(candidate),
                    modality_origin=modality,
                )
            )
            continue
        if not _is_question_like(candidate) and not is_interview_question(candidate):
            continue
        candidate = clean_question_text(candidate)
        if is_low_quality_question(candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Question(
                text=candidate,
                source_refs=[post.url] if post.url else [],
                freq=1,
                latest_posted_at=post.posted_at,
                role_tags=list(role_tags),
                company_tags=list(company_tags),
                topic=infer_topic(candidate),
                modality_origin=modality,
            )
        )
    return out


def extract_questions(posts: list[RawPost]) -> list[Question]:
    questions: list[Question] = []
    for post in posts:
        questions.extend(extract_questions_from_post(post))
    return questions
