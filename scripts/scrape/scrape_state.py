"""Persistent state for daily incremental scraping (keyword queue + known IDs)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import cache_dir
from scripts.corpus.post_dedupe import post_dedupe_key
from scripts.models import RawPost


def scrape_state_path() -> Path:
    return cache_dir() / "daily" / "scrape_state.json"


def rolling_nowcoder_path() -> Path:
    return cache_dir() / "daily" / "rolling_nowcoder_posts.json"


def _today_iso() -> str:
    return date.today().isoformat()


def load_scrape_state() -> dict[str, Any]:
    path = scrape_state_path()
    if not path.is_file():
        return {
            "version": 1,
            "xhs_queue_offset": 0,
            "xhs_known_note_ids": [],
            "nowcoder_known_keys": [],
            "query_last_run": {},
            "full_scrape_nc_done": [],
            "last_daily_run": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 1,
            "xhs_queue_offset": 0,
            "xhs_known_note_ids": [],
            "nowcoder_known_keys": [],
            "query_last_run": {},
            "full_scrape_nc_done": [],
            "last_daily_run": None,
        }
    if not isinstance(data, dict):
        return {
            "version": 1,
            "xhs_queue_offset": 0,
            "xhs_known_note_ids": [],
            "nowcoder_known_keys": [],
            "query_last_run": {},
            "full_scrape_nc_done": [],
            "last_daily_run": None,
        }
    data.setdefault("version", 1)
    data.setdefault("xhs_known_note_ids", [])
    data.setdefault("nowcoder_known_keys", [])
    data.setdefault("query_last_run", {})
    data.setdefault("full_scrape_nc_done", [])
    return data


def save_scrape_state(state: dict[str, Any]) -> Path:
    path = scrape_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def pick_xhs_keyword_batch(
    keywords: list[str],
    state: dict[str, Any],
    *,
    per_day: int,
) -> list[str]:
    if not keywords or per_day <= 0:
        return []
    offset = int(state.get("xhs_queue_offset") or 0) % len(keywords)
    batch: list[str] = []
    for i in range(min(per_day, len(keywords))):
        batch.append(keywords[(offset + i) % len(keywords)])
    state["xhs_queue_offset"] = (offset + len(batch)) % len(keywords)
    return batch


def pick_nowcoder_query_batch(
    queries: list[str],
    state: dict[str, Any],
    *,
    per_day: int,
    min_days_between: int = 1,
) -> list[str]:
    if not queries or per_day <= 0:
        return []
    today = date.today()
    last_run: dict[str, str] = dict(state.get("query_last_run") or {})
    stale: list[str] = []
    for q in queries:
        ran = last_run.get(q)
        if not ran:
            stale.append(q)
            continue
        try:
            prev = date.fromisoformat(ran)
        except ValueError:
            stale.append(q)
            continue
        if (today - prev).days >= min_days_between:
            stale.append(q)
    if not stale:
        stale = list(queries)
    batch = stale[:per_day]
    for q in batch:
        last_run[q] = _today_iso()
    state["query_last_run"] = last_run
    return batch


def register_xhs_note_ids(state: dict[str, Any], note_ids: list[str]) -> int:
    known = set(state.get("xhs_known_note_ids") or [])
    added = 0
    for nid in note_ids:
        nid = str(nid).strip()
        if nid and nid not in known:
            known.add(nid)
            added += 1
    state["xhs_known_note_ids"] = sorted(known)
    return added


def filter_new_nowcoder_posts(
    posts: list[RawPost],
    state: dict[str, Any],
) -> list[RawPost]:
    known = set(state.get("nowcoder_known_keys") or [])
    new_posts: list[RawPost] = []
    for post in posts:
        key = post_dedupe_key(post)
        if not key or key in known:
            continue
        known.add(key)
        new_posts.append(post)
    state["nowcoder_known_keys"] = sorted(known)
    return new_posts


def mark_full_scrape_queries_done(queries: list[str], state: dict[str, Any] | None = None) -> int:
    """Record completed Nowcoder queries during a full scrape run."""
    st = state if state is not None else load_scrape_state()
    done = set(st.get("full_scrape_nc_done") or [])
    added = 0
    for q in queries:
        q = q.strip()
        if q and q not in done:
            done.add(q)
            added += 1
    st["full_scrape_nc_done"] = sorted(done)
    if state is None:
        save_scrape_state(st)
    return added


def full_scrape_nc_done_queries(state: dict[str, Any] | None = None) -> set[str]:
    st = state if state is not None else load_scrape_state()
    return set(st.get("full_scrape_nc_done") or [])


def clear_full_scrape_nc_progress(state: dict[str, Any] | None = None) -> None:
    st = state if state is not None else load_scrape_state()
    st["full_scrape_nc_done"] = []
    if state is None:
        save_scrape_state(st)


def append_rolling_nowcoder_posts(new_posts: list[RawPost]) -> int:
    path = rolling_nowcoder_path()
    existing: list[dict] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = []
    seen = {post_dedupe_key(RawPost.from_dict(d)) for d in existing}
    added = 0
    for post in new_posts:
        key = post_dedupe_key(post)
        if not key or key in seen:
            continue
        seen.add(key)
        existing.append(post.to_dict())
        added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def collect_note_ids_from_export_files(paths: list[Path]) -> list[str]:
    ids: list[str] = []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        notes = raw if isinstance(raw, list) else raw.get("notes") or raw.get("data") or []
        if not isinstance(notes, list):
            continue
        for note in notes:
            if isinstance(note, dict) and note.get("note_id"):
                ids.append(str(note["note_id"]))
    return ids
