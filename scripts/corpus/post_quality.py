"""Filter scraped posts: keep interview experiences, drop ads and off-topic chatter."""
from __future__ import annotations

import re
from typing import Literal

from scripts.corpus.role_match import post_text_blob
from scripts.models import RawPost

RuleVerdict = Literal["keep", "drop", "review"]

_AD = re.compile(
    r"(?:"
    r"内推码|内推链接|简历代投|保offer|保录|"
    r"诚聘|急聘|招聘岗位|岗位要求|职位描述|"
    r"培训班|辅导课|1v1辅导|求职辅导|"
    r"私信我|加我微信|加群|领资料|扫码|"
    r"兼职日结|日结兼职|微信同号|vx同|"
    r"广告合作|品牌推广|有偿|代写简历"
    r")",
    re.I,
)
_CHATTER = re.compile(
    r"(?:"
    r"点赞\s*收藏|关注不迷路|转发扩散|"
    r"仅供参考|经验之谈|友情提示"
    r")",
    re.I,
)
_DISCUSSION = re.compile(
    r"(?:"
    r"就业方向|选什么(?:方向)?|应该选什么|大家觉得|"
    r"哪个方向好|该不该学|值不值得|"
    r"没什么面试|感觉.{0,6}没.{0,4}面试|"
    r"暑期.{0,4}gg|秋招.{0,6}选什么"
    r")",
    re.I,
)
_INTERVIEW = re.compile(
    r"(?:"
    r"面经|凉经|进面|"
    r"一面|二面|三面|四面|HR面|hr面|"
    r"面试题|面试经验|面试分享|面试记录|"
    r"面试官|笔试|手撕|拷打|"
    r"问了什么|问了哪些|考察了|问了下|"
    r"技术面|群面|无领导|"
    r"自我介绍|项目经历|项目细节"
    r")",
    re.I,
)
_NUMBERED = re.compile(r"(?:^|\n)\s*\d+[\.\、\)）]\s*\S+")
_QUESTION_MARK = re.compile(r"[？?]")
_TOPIC_ONLY = re.compile(r"^[\s#\d就业方向话题面经分享记录]+$", re.I)
_EMOJI_HEAVY = re.compile(r"[\U0001F300-\U0001FAFF😀-🙏🌀-🗿]{3,}")
_OCR_JUNK = re.compile(
    r"(?:"
    r"补偿邮件|异常对局|G\.T\.I|SECURITY|"
    r"游戏邮件|装备返还|对局补偿|"
    r"系统邮件|邮件\d+/\d+"
    r")",
    re.I,
)


def _has_images(post: RawPost) -> bool:
    return bool(post.asset_paths) or bool((post.image_ocr_text or "").strip())


def _interview_signals(blob: str, ocr: str = "") -> tuple[bool, bool, bool]:
    has_interview = bool(_INTERVIEW.search(blob)) or bool(_INTERVIEW.search(ocr))
    has_numbered = bool(_NUMBERED.search(blob)) or bool(_NUMBERED.search(ocr))
    has_question = bool(_QUESTION_MARK.search(blob))
    return has_interview, has_numbered, has_question


def rule_post_verdict(post: RawPost) -> RuleVerdict:
    """keep/drop without AI; review = send to DeepSeek."""
    blob = post_text_blob(post).strip()
    ocr = (post.image_ocr_text or "").strip()
    if not blob and not _has_images(post):
        return "drop"

    compact = re.sub(r"\s+", "", blob)
    has_interview, has_numbered, has_question = _interview_signals(blob, ocr)

    if has_interview or has_numbered:
        return "keep"

    if _TOPIC_ONLY.match(blob.replace("#", " ").strip()):
        return "drop"

    if _OCR_JUNK.search(blob) or _OCR_JUNK.search(ocr):
        return "drop"

    if _AD.search(blob) and not has_interview and not has_numbered:
        return "drop"

    if _CHATTER.search(blob) and not has_interview and not has_numbered:
        return "drop"

    if _DISCUSSION.search(blob) and not has_interview and not has_numbered:
        return "drop"

    if len(compact) < 12 and not _has_images(post):
        return "drop"

    if len(compact) < 80 and not has_interview and not has_numbered:
        if _DISCUSSION.search(blob) or _EMOJI_HEAVY.search(blob):
            return "drop"
        if not has_question and not _has_images(post):
            return "drop"

    # Tech keywords / short caption + images → AI
    if _has_images(post) and not has_interview and not has_numbered:
        return "review"

    if len(compact) < 120 and not has_interview and not has_numbered:
        return "review"

    if _DISCUSSION.search(blob) or _AD.search(blob) or _CHATTER.search(blob):
        return "review"

    return "keep"


def is_interview_experience_post(post: RawPost) -> bool:
    """True when post looks like an interview recap (rules only, no AI)."""
    verdict = rule_post_verdict(post)
    if verdict == "keep":
        return True
    if verdict == "drop":
        return False
    return True


def filter_interview_experience_posts(posts: list[RawPost]) -> tuple[list[RawPost], list[RawPost]]:
    from scripts.corpus.post_ai_filter import filter_interview_experience_posts_hybrid

    kept, dropped, _meta = filter_interview_experience_posts_hybrid(posts)
    return kept, dropped
