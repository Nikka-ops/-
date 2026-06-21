"""Rule + DeepSeek AI filter for borderline interview posts."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import requests

from scripts.config import (
    cache_dir,
    deepseek_api_key,
    deepseek_api_base,
    deepseek_model,
    post_ai_filter_enabled,
    post_ai_filter_max_chars,
)
from scripts.corpus.post_quality import rule_post_verdict
from scripts.corpus.post_text_merge import strip_ocr_page_markers
from scripts.corpus.role_match import post_text_blob
from scripts.models import RawPost

RuleVerdict = Literal["keep", "drop", "review"]

_SYSTEM = (
    "你是面经库质检员。判断用户帖子是否为「面试经历复盘」："
    "包含某公司/岗位的面试过程、被问到的题目、项目拷打、笔试手撕、凉经等。"
    "不是面经：就业方向闲聊、选岗求助、内推招聘广告、培训班广告、纯吐槽无面试细节、仅话题标签。"
    "只输出 JSON：{\"keep\": true或false, \"reason\": \"不超过40字\"}"
)


def _cache_path() -> Path:
    path = cache_dir() / "daily" / "post_ai_filter_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _post_key(post: RawPost) -> str:
    url = (post.url or "").strip()
    if url:
        return url
    blob = post_text_blob(post)[:200]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _snippet_for_ai(post: RawPost, max_chars: int) -> str:
    blob = strip_ocr_page_markers(post_text_blob(post))
    blob = re.sub(r"\s+", " ", blob).strip()
    if len(blob) <= max_chars:
        return blob
    return blob[:max_chars].rstrip() + "…"


def _load_cache() -> dict:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    path = _cache_path()
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_ai_json(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        keep = bool(data.get("keep"))
        reason = str(data.get("reason") or "").strip()[:80]
        return keep, reason
    except json.JSONDecodeError:
        low = raw.lower()
        if '"keep": true' in low or '"keep":true' in low:
            return True, raw[:80]
        if '"keep": false' in low or '"keep":false' in low:
            return False, raw[:80]
        return False, "ai_parse_error"


def deepseek_classify_post(snippet: str, *, timeout: float = 25.0) -> tuple[bool, str]:
    key = deepseek_api_key()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")
    url = f"{deepseek_api_base()}/v1/chat/completions"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": deepseek_model(),
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": snippet},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _parse_ai_json(str(content))


def ai_review_post(post: RawPost, cache: dict | None = None) -> tuple[bool, str, bool]:
    """Return (keep, reason, from_cache)."""
    key = _post_key(post)
    store = cache if cache is not None else _load_cache()
    if key in store:
        row = store[key]
        return bool(row.get("keep")), str(row.get("reason") or ""), True

    snippet = _snippet_for_ai(post, post_ai_filter_max_chars())
    if not snippet:
        return False, "empty_snippet", False

    keep, reason = deepseek_classify_post(snippet)
    store[key] = {
        "keep": keep,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if cache is None:
        _save_cache(store)
    return keep, reason, False


def filter_interview_experience_posts_hybrid(
    posts: list[RawPost],
    *,
    use_ai: bool | None = None,
    request_delay: float = 0.15,
) -> tuple[list[RawPost], list[RawPost], dict]:
    """Rules first; DeepSeek only for `review` verdicts."""
    use_ai = post_ai_filter_enabled() if use_ai is None else use_ai
    if use_ai and not deepseek_api_key():
        use_ai = False

    cache = _load_cache() if use_ai else {}
    kept: list[RawPost] = []
    dropped: list[RawPost] = []
    meta: dict = {
        "ai_enabled": use_ai,
        "rule_keep": 0,
        "rule_drop": 0,
        "ai_review": 0,
        "ai_keep": 0,
        "ai_drop": 0,
        "ai_cache_hits": 0,
        "ai_errors": 0,
    }

    for i, post in enumerate(posts):
        verdict = rule_post_verdict(post)
        if verdict == "keep":
            meta["rule_keep"] += 1
            kept.append(post)
            continue
        if verdict == "drop":
            meta["rule_drop"] += 1
            dropped.append(post)
            continue

        meta["ai_review"] += 1
        if not use_ai:
            kept.append(post)
            continue

        if i and request_delay > 0:
            time.sleep(request_delay)
        try:
            keep, reason, cached = ai_review_post(post, cache=cache)
            if cached:
                meta["ai_cache_hits"] += 1
            if keep:
                meta["ai_keep"] += 1
                kept.append(post)
            else:
                meta["ai_drop"] += 1
                dropped.append(post)
        except Exception as exc:  # noqa: BLE001
            meta["ai_errors"] += 1
            # Fail open on API errors: keep borderline posts
            kept.append(post)
            meta.setdefault("ai_error_samples", []).append(str(exc)[:120])

    if use_ai and cache:
        _save_cache(cache)

    return kept, dropped, meta
