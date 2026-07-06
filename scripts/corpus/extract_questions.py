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
# Rules are applied in ORDER — put specific tech keywords FIRST, broad patterns LAST.
_TOPIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    # AI-specific (most distinctive, check first)
    ("RAG", re.compile(r"rag|检索增强|召回率|embedding|向量(?:数据库|检索)|rerank|切块|chunk", re.I)),
    ("Agent", re.compile(r"\bagent\b|react\s*框架|plan.?execute|多智能体|工具调用|function.?call|tool\s*use", re.I)),
    ("MCP/协议", re.compile(r"\bmcp\b|function.?calling|structured.?output|json.?mode", re.I)),
    ("LLM基础", re.compile(r"transformer|attention机制|qkv|rope|位置编码|微调|sft|lora|rlhf|ppo|dpo|kv.?cache", re.I)),
    # Data engineering (tech-specific, check before broad patterns)
    ("Spark/计算", re.compile(r"\bspark\b|shuffle|宽依赖|窄依赖|\brdd\b|dataframe.*spark|spark.*dataframe|stage.*dag|spark.*内存", re.I)),
    ("Flink/实时", re.compile(r"\bflink\b|checkpoint|watermark|双流.*join|实时.*计算|流批.*一体|状态.*后端", re.I)),
    ("Hive/SQL", re.compile(r"\bhive\b|hql|分区.*分桶|mapreduce|\bmr\b|sql.*优化|执行计划|索引.*查询|窗口函数", re.I)),
    ("数仓建模", re.compile(r"\bods\b|\bdwd\b|\bdws\b|\bads\b|维度.*事实|数据分层|星型.*模型|雪花.*模型|宽表|拉链表", re.I)),
    ("数据工程", re.compile(r"\betl\b|任务调度|airflow|dolphin.*scheduler|数据质量|数据血缘|湖仓|iceberg|hudi|delta.*lake", re.I)),
    # Coding
    ("手撕代码", re.compile(r"手撕|leetcode|力扣|coding\s*题|算法题|写.*代码|实现.*算法", re.I)),
    # Broader patterns — must come after specific ones
    ("后端八股", re.compile(r"redis|mysql|kafka|tcp/ip|线程.*进程|synchronized|jvm|spring(?:boot)?|分布式.*锁", re.I)),
    ("项目深挖", re.compile(r"项目.*难点|项目.*挑战|项目.*优化|系统设计|压测|qps.*tps|部署.*方案|架构.*演进", re.I)),
    ("产品/业务", re.compile(r"业务.*指标|ab.*实验|用户.*增长|漏斗|埋点|gmv|dau|留存", re.I)),
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
    from scripts.corpus.company_normalize import normalize_company_name

    company = normalize_company_name(post.company) if post.company else None
    company_tags = [company] if company else []
    role_tags = [post.role] if post.role else []
    modality = _modality_from_post(post)
    # Use AI-inferred topic hints from post if available; fall back to per-line regex
    post_topic_hint = post.ai_topics[0] if getattr(post, "ai_topics", None) else None
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
                    topic=infer_topic(candidate) or post_topic_hint or "综合",
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
