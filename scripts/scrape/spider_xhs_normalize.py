"""Convert Spider_XHS note payloads into normalize_xhs / XiaohongshuConnector schema."""
from __future__ import annotations

from datetime import datetime, timezone


def _upload_time_to_ms(upload_time: str | None) -> int:
    text = (upload_time or "").strip()
    if not text:
        return 0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return 0


def note_from_handled(handled: dict) -> dict:
    """Map ``handle_note_info`` output → MediaCrawler-compatible note dict."""
    return {
        "note_id": handled.get("note_id") or "",
        "note_url": handled.get("note_url") or "",
        "title": handled.get("title") or "",
        "desc": handled.get("desc") or "",
        "time": _upload_time_to_ms(handled.get("upload_time")),
        "image_list": list(handled.get("image_list") or []),
        "tags": list(handled.get("tags") or []),
    }


def note_from_search_item(item: dict) -> dict | None:
    """Best-effort note dict from search API item (no detail fetch)."""
    if item.get("model_type") != "note":
        return None
    note_id = str(item.get("id") or "").strip()
    if not note_id:
        return None
    card = item.get("note_card") or {}
    xsec = str(item.get("xsec_token") or "").strip()
    note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec:
        note_url += f"?xsec_token={xsec}"
    title = (card.get("title") or card.get("display_title") or "").strip()
    desc = (card.get("desc") or "").strip()
    image_list: list[str] = []
    for image in card.get("image_list") or []:
        if not isinstance(image, dict):
            continue
        added = False
        for info in image.get("info_list") or []:
            if isinstance(info, dict) and info.get("url"):
                image_list.append(str(info["url"]))
                added = True
                break
        if not added and image.get("url_default"):
            image_list.append(str(image["url_default"]))
    tags: list[str] = []
    for tag in card.get("tag_list") or []:
        if isinstance(tag, dict) and tag.get("name"):
            tags.append(str(tag["name"]))
    time_ms = 0
    if card.get("time"):
        try:
            time_ms = int(card["time"])
        except (TypeError, ValueError):
            time_ms = 0
    return {
        "note_id": note_id,
        "note_url": note_url,
        "title": title,
        "desc": desc,
        "time": time_ms,
        "image_list": image_list,
        "tags": tags,
    }
