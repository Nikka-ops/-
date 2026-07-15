"""Post ingest: agent gate + offline fallback."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from scripts.config import deepseek_api_key, focus_role_ids
from scripts.corpus.ai_gate import ai_enabled, cached_post_keep, judge_post, load_cache, offline_post_keep, save_cache
from scripts.corpus.post_text_merge import strip_ocr_page_markers
from scripts.corpus.role_match import filter_posts_for_bank, post_combined_text, refine_extracted_role
from scripts.corpus.tech_roles import canonical_role_id, resolve_role_label
from scripts.models import RawPost

_CACHE = "post_ai_filter_cache.json"
_FLUSH = 40
_AI_WORKERS = 8  # concurrent DeepSeek judge calls; serial was ~1.7s/post


def _has_images(post: RawPost) -> bool:
    return bool(post.asset_paths)


def _offline_keep(post: RawPost) -> bool:
    return offline_post_keep(post_combined_text(post), has_images=_has_images(post))


def ingest_drop_reason(post: RawPost) -> str | None:
    combined = post_combined_text(post)
    if not combined and not _has_images(post):
        return "junk"
    if ai_enabled():
        v = cached_post_keep(post.url or "", combined)
        if v is False:
            return "ai_dropped"
        if v is None and not _offline_keep(post):
            return "not_recap"
        return None
    return None if _offline_keep(post) else "not_recap"


def should_drop(post: RawPost) -> bool:
    return ingest_drop_reason(post) is not None


def should_display_post(post: RawPost) -> bool:
    return ingest_drop_reason(post) is None


def _set_role(post: RawPost, role_id: str | None) -> None:
    rid = canonical_role_id(role_id or "")
    if rid in set(focus_role_ids()):
        post.role = resolve_role_label(role_id=rid)
        return
    head = (post_combined_text(post).splitlines() or [""])[0][:160]
    if r := refine_extracted_role(title=head, desc=post_combined_text(post), parsed_role=post.role):
        post.role = r


def filter_ingest_posts(
    posts: list[RawPost],
    role: str,
    *,
    skip_role: bool = False,
    use_ai: bool | None = None,
) -> tuple[list[RawPost], dict]:
    use_ai = ai_enabled() if use_ai is None else use_ai
    if use_ai and not deepseek_api_key():
        use_ai = False
    bank_rid = canonical_role_id(role or "")
    cache = load_cache(_CACHE) if use_ai else {}
    meta: dict = {"ai_enabled": use_ai, "input": len(posts)}
    kept: list[RawPost] = []
    focus = set(focus_role_ids())

    candidates: list[RawPost] = []
    for post in posts:
        combined = post_combined_text(post)
        if not combined and not _has_images(post):
            meta["junk_dropped"] = meta.get("junk_dropped", 0) + 1
            continue
        if not use_ai:
            if _offline_keep(post):
                kept.append(post)
            else:
                meta["offline_dropped"] = meta.get("offline_dropped", 0) + 1
            continue
        candidates.append(post)

    if use_ai and candidates:
        # cache is a plain dict shared across workers: judge_post only does
        # single-key reads/writes, which are atomic under the GIL.
        def _judge(post: RawPost):
            snip = re.sub(r"\s+", " ", strip_ocr_page_markers(post_combined_text(post)))[:900]
            return post, judge_post(snip, url=post.url or "", cache=cache)

        done = 0
        with ThreadPoolExecutor(max_workers=_AI_WORKERS) as pool:
            for post, verdict in pool.map(_judge, candidates):
                done += 1
                if verdict is None:
                    meta["ai_errors"] = meta.get("ai_errors", 0) + 1
                    fb = "ai_fallback_kept" if _offline_keep(post) else "ai_fallback_dropped"
                    meta[fb] = meta.get(fb, 0) + 1
                    if fb.endswith("kept"):
                        kept.append(post)
                elif not verdict.keep or (verdict.role_id and canonical_role_id(verdict.role_id) not in focus):
                    meta["ai_dropped"] = meta.get("ai_dropped", 0) + 1
                elif bank_rid and canonical_role_id(verdict.role_id or "") != bank_rid:
                    # AI says another focus role (ai_app post in a data bank) or no target role
                    # at all (role_id=null: bank/hardware/off-role recaps) — keep banks role-pure.
                    meta["role_dropped_ai"] = meta.get("role_dropped_ai", 0) + 1
                else:
                    _set_role(post, verdict.role_id)
                    if verdict.topics:
                        post.ai_topics = verdict.topics
                    kept.append(post)
                if cache and done % _FLUSH == 0:
                    save_cache(_CACHE, cache)

    if use_ai and cache:
        save_cache(_CACHE, cache)
    # When AI ran, role purity is enforced above via verdict.role_id; the regex
    # bank filter is too aggressive on AI-kept posts (drops valid recaps), so skip it.
    if skip_role or use_ai:
        meta["kept"] = len(kept)
        return kept, meta
    kept, dropped = filter_posts_for_bank(kept, role)
    meta["role_dropped"] = len(dropped)
    meta["kept"] = len(kept)
    return kept, meta
