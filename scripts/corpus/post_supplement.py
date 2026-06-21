"""Merge role-matched posts from saved banks and local corpus files."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.corpus.bank_cache import list_banks, load_cached_raw_posts
from scripts.corpus.ingest_fallback import corpus_path_matches_role, load_report_hints
from scripts.corpus.role_match import annotate_post
from scripts.corpus.tech_roles import get_tech_role
from scripts.models import RawPost

_SPACE = re.compile(r"\s+")


def _norm_role(text: str) -> str:
    return _SPACE.sub("", (text or "").strip().lower())


def _role_matches_bank(role: str, role_id: str, bank_meta: dict) -> bool:
    if role_id and bank_meta.get("role_id") == role_id:
        return True
    bank_role = bank_meta.get("role") or ""
    if _norm_role(bank_role) and _norm_role(bank_role) == _norm_role(role):
        return True
    preset = get_tech_role(role_id or "")
    if preset and _norm_role(bank_role) == _norm_role(preset.search_as):
        return True
    return False


def _load_posts_from_json(path: Path) -> list[RawPost]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [RawPost.from_dict(d) for d in data if isinstance(d, dict)]
    if isinstance(data, dict) and isinstance(data.get("posts"), list):
        return [RawPost.from_dict(d) for d in data["posts"] if isinstance(d, dict)]
    return []


def _local_corpus_paths(cache_parent: Path) -> list[Path]:
    paths: list[Path] = []
    if not cache_parent.is_dir():
        return paths
    patterns = (
        "raw_posts_*.json",
        "raw_posts_all.json",
        "retry_raw_posts.json",
        "role_batch_*.json",
        "scrape_smoke_report.json",
        "*scrape*report*.json",
    )
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(cache_parent.glob(pattern)):
            if path.is_file() and str(path) not in seen:
                seen.add(str(path))
                paths.append(path)
    return paths


def supplement_posts_for_role(
    posts: list[RawPost],
    role: str,
    role_id: str,
    cache_root: Path,
) -> tuple[list[RawPost], dict]:
    """Append role-matched posts from other banks and corpus_cache JSON dumps."""
    seen_urls: set[str] = {p.url for p in posts if p.url}
    seen_text: set[str] = set()
    for p in posts:
        key = (p.raw_text or "")[:200].strip()
        if key:
            seen_text.add(key)

    merged = list(posts)
    meta: dict = {"from_banks": 0, "from_files": 0, "paths": []}

    banks_root = cache_root
    if banks_root.is_dir():
        for bank in list_banks(banks_root):
            if not _role_matches_bank(role, role_id, bank):
                continue
            slug = bank.get("slug") or ""
            if not slug:
                continue
            cached = load_cached_raw_posts(banks_root, slug) or []
            for post in cached:
                url = post.url or ""
                text_key = (post.raw_text or "")[:200].strip()
                if url and url in seen_urls:
                    continue
                if text_key and text_key in seen_text:
                    continue
                merged.append(post)
                if url:
                    seen_urls.add(url)
                if text_key:
                    seen_text.add(text_key)
                meta["from_banks"] += 1

    cache_parent = banks_root.parent if banks_root.name == "banks" else banks_root
    all_json = cache_parent / "raw_posts_all.json"
    if all_json.is_file() and str(all_json) not in {str(p) for p in _local_corpus_paths(cache_parent)}:
        for post in _load_posts_from_json(all_json):
            url = post.url or ""
            text_key = (post.raw_text or "")[:200].strip()
            if url and url in seen_urls:
                continue
            if text_key and text_key in seen_text:
                continue
            merged.append(annotate_post(post))
            if url:
                seen_urls.add(url)
            if text_key:
                seen_text.add(text_key)
            meta["from_files"] += 1
            if "raw_posts_all.json" not in meta["paths"]:
                meta["paths"].append("raw_posts_all.json")

    for path in _local_corpus_paths(cache_parent):
        hints = load_report_hints(path)
        if not corpus_path_matches_role(role, path) and not _file_role_id_matches(path, role_id):
            continue
        for post in _load_posts_from_json(path):
            url = post.url or ""
            text_key = (post.raw_text or "")[:200].strip()
            if url and url in seen_urls:
                continue
            if text_key and text_key in seen_text:
                continue
            merged.append(annotate_post(post))
            if url:
                seen_urls.add(url)
            if text_key:
                seen_text.add(text_key)
            meta["from_files"] += 1
            meta["paths"].append(str(path.name))

    meta["total_after_supplement"] = len(merged)
    return merged, meta


def _file_role_id_matches(path: Path, role_id: str) -> bool:
    if not role_id:
        return False
    name = path.stem.lower()
    if name.startswith("role_batch_"):
        batch_id = name.replace("role_batch_", "")
        return batch_id == role_id or batch_id.replace("_", "") == role_id.replace("_", "")
    return False
