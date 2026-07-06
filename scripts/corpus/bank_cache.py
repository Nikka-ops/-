"""Persistent question-bank cache keyed by role (+ optional companies)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.corpus.posts_view import company_options_from_dicts, serialize_posts
from scripts.corpus.question_bank_view import serialize_question_bank_ui
from scripts.corpus.quality import filter_question_dicts, is_interview_question
from scripts.corpus.role_match import annotate_post
from scripts.corpus.store import load_raw_posts, save_raw_posts
from scripts.corpus.tech_roles import canonical_role_id, equivalent_role_ids
from scripts.models import RawPost, Question

_SLUG_SAFE = re.compile(r"[^\w\u4e00-\u9fff+-]+")


def bank_slug(role: str, companies: list[str] | None = None) -> str:
    parts = [role.strip()]
    if companies:
        parts.extend(sorted({c.strip() for c in companies if c.strip()}))
    raw = "__".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    label = _SLUG_SAFE.sub("_", raw)[:48].strip("_") or "bank"
    return f"{label}_{digest}"


def bank_dir(cache_root: Path, slug: str) -> Path:
    return cache_root / slug


def meta_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "meta.json"


def raw_posts_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "raw_posts.json"


def questions_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "questions_ranked.json"


def question_bank_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "question_bank.json"


def frequency_report_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "frequency_report.md"


def prep_package_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "prep_package.md"


def predicted_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "predicted_questions.json"


def agent_handoff_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "agent_handoff.md"


def agent_context_path(cache_root: Path, slug: str) -> Path:
    return bank_dir(cache_root, slug) / "agent_context.json"


def is_fresh(cache_root: Path, slug: str, ttl_days: int, today: date | None = None) -> bool:
    mp = meta_path(cache_root, slug)
    if not mp.is_file():
        return False
    meta = json.loads(mp.read_text(encoding="utf-8"))
    updated = meta.get("updated_at")
    if not updated:
        return False
    try:
        ts = datetime.fromisoformat(updated).date()
    except ValueError:
        return False
    ref = today or date.today()
    return (ref - ts).days < ttl_days


def write_meta(
    cache_root: Path,
    slug: str,
    *,
    role: str,
    companies: list[str],
    post_count: int,
    question_count: int,
    sources: dict,
    role_id: str | None = None,
) -> None:
    d = bank_dir(cache_root, slug)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "role": role,
        "role_id": role_id or "",
        "companies": companies,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "post_count": post_count,
        "question_count": question_count,
        "sources": sources,
        "paths": {
            "raw_posts": str(raw_posts_path(cache_root, slug)),
            "question_bank": str(question_bank_path(cache_root, slug)),
            "frequency_report": str(frequency_report_path(cache_root, slug)),
        },
    }
    meta_path(cache_root, slug).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_cached_raw_posts(cache_root: Path, slug: str) -> list[RawPost] | None:
    path = raw_posts_path(cache_root, slug)
    if not path.is_file():
        return None
    return load_raw_posts(path)


def load_question_bank(cache_root: Path, slug: str) -> dict | None:
    path = question_bank_path(cache_root, slug)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_frequency_report(cache_root: Path, slug: str) -> str:
    path = frequency_report_path(cache_root, slug)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def load_bank_meta(cache_root: Path, slug: str) -> dict | None:
    path = meta_path(cache_root, slug)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_banks(cache_root: Path) -> list[dict]:
    """List saved question banks (newest first)."""
    if not cache_root.is_dir():
        return []
    rows: list[dict] = []
    for entry in cache_root.iterdir():
        if not entry.is_dir():
            continue
        slug = entry.name
        meta = load_bank_meta(cache_root, slug)
        bank = load_question_bank(cache_root, slug)
        if not meta or not bank:
            continue
        rows.append(
            {
                "slug": slug,
                "role": meta.get("role") or bank.get("role"),
                "role_id": meta.get("role_id") or "",
                "companies": meta.get("companies") or bank.get("companies") or [],
                "updated_at": meta.get("updated_at"),
                "post_count": meta.get("post_count") or bank.get("post_count"),
                "question_count": meta.get("question_count") or bank.get("question_count"),
            }
        )
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows


def _norm_role_label(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _post_has_local_assets(post: RawPost) -> bool:
    for raw in post.asset_paths or []:
        path = str(raw).strip()
        if path and not path.lower().startswith("http"):
            return True
    return False


_MERGED_AI_ROLE_NORMS = frozenset(
    {
        _norm_role_label("AI应用开发"),
        _norm_role_label("AI 应用开发"),
        _norm_role_label("Agent开发"),
        _norm_role_label("AI/Agent 应用开发"),
    }
)


def _sanitize_bank(bank: dict | None) -> dict | None:
    if not bank:
        return bank
    out = dict(bank)
    questions = filter_question_dicts(out.get("questions") or [])
    out["questions"] = questions
    clusters = out.get("clusters") or []
    out["clusters"] = [
        c
        for c in clusters
        if is_interview_question(c.get("representative") or c.get("text") or "")
    ]
    out["question_count"] = len(questions)
    out["cluster_count"] = len(out["clusters"])
    return out


def banks_matching_role(
    cache_root: Path,
    role: str,
    companies: list[str] | None = None,
    role_id: str | None = None,
) -> list[dict]:
    all_rows = list_banks(cache_root)
    rid = canonical_role_id(role_id) if role_id else ""
    pool = all_rows

    if rid:
        ids = set(equivalent_role_ids(rid))
        by_id = [r for r in all_rows if r.get("role_id") in ids]
        if by_id:
            pool = by_id

    target = _norm_role_label(role)
    if target and (not rid or pool == all_rows):
        label_pool: list[dict] = []
        for row in all_rows:
            rn = _norm_role_label(row.get("role") or "")
            if rn == target or (rid == "ai_app" and rn in _MERGED_AI_ROLE_NORMS):
                label_pool.append(row)
        if label_pool:
            pool = label_pool

    companies_norm = [_norm_role_label(c) for c in (companies or []) if c and c.strip()]
    matched: list[dict] = []
    for row in pool:
        if target and rid != "ai_app":
            rn = _norm_role_label(row.get("role") or "")
            if rn != target and rn not in _MERGED_AI_ROLE_NORMS:
                continue
        bank_cos = [_norm_role_label(c) for c in (row.get("companies") or [])]
        if companies_norm:
            if not bank_cos:
                continue
            if not any(
                cn == bc or cn in bc or bc in cn for cn in companies_norm for bc in bank_cos
            ):
                continue
        matched.append(row)
    matched.sort(key=lambda r: -(r.get("post_count") or 0))
    return matched


def load_merged_role_bundle(
    cache_root: Path,
    role: str,
    companies: list[str] | None = None,
    role_id: str | None = None,
) -> dict | None:
    """Merge raw posts from all cached banks for the same role (dedupe by URL)."""
    rows = banks_matching_role(cache_root, role, companies, role_id=role_id)
    if not rows:
        return None

    all_raw: list[RawPost] = []
    seen: dict[str, int] = {}
    primary_slug = rows[0]["slug"]
    bank: dict | None = None
    frequency = ""
    meta: dict = {}

    for row in rows:
        slug = row["slug"]
        for post in load_cached_raw_posts(cache_root, slug) or []:
            url = (post.url or "").strip()
            if url and url != "https://www.nowcoder.com/":
                key = url
            else:
                key = (post.raw_text or post.content_text or "")[:200]
            if not key:
                continue
            if key in seen:
                existing = all_raw[seen[key]]
                if _post_has_local_assets(post) and not _post_has_local_assets(existing):
                    all_raw[seen[key]] = post
                continue
            seen[key] = len(all_raw)
            all_raw.append(post)
        if slug == primary_slug:
            bank = _sanitize_bank(load_question_bank(cache_root, slug))
            frequency = load_frequency_report(cache_root, slug)
            meta = load_bank_meta(cache_root, slug) or {}

    bank_role = role or meta.get("role") or (bank.get("role") if bank else "") or ""
    all_raw = [annotate_post(p) for p in all_raw]
    posts = serialize_posts(all_raw, bank_role=bank_role, for_display=True)
    posts = [p for p in posts if not p.get("role_mismatch")]
    posts.sort(key=lambda r: (r.get("posted_at") or "", r.get("title") or ""), reverse=True)
    question_bank_ui = serialize_question_bank_ui(bank, posts)

    return {
        "slug": primary_slug,
        "merged_slugs": [r["slug"] for r in rows],
        "bank": bank,
        "posts": posts,
        "question_bank_ui": question_bank_ui,
        "companies": company_options_from_dicts(posts),
        "frequency_report": frequency,
        "meta": meta,
        "paths": {
            "question_bank": str(question_bank_path(cache_root, primary_slug)),
            "frequency_report": str(frequency_report_path(cache_root, primary_slug)),
            "raw_posts": str(raw_posts_path(cache_root, primary_slug)),
        },
    }


def load_bank_bundle(cache_root: Path, slug: str) -> dict | None:
    """Load question bank + raw posts + frequency report + meta for read-only API."""
    bank = load_question_bank(cache_root, slug)
    if bank is None:
        return None
    bank = _sanitize_bank(bank)
    meta = load_bank_meta(cache_root, slug) or {}
    raw_posts = load_cached_raw_posts(cache_root, slug) or []
    bank_role = meta.get("role") or bank.get("role") or ""
    raw_posts = [annotate_post(p) for p in raw_posts]
    posts = serialize_posts(raw_posts, bank_role=bank_role, for_display=True)
    posts = [p for p in posts if not p.get("role_mismatch")]
    question_bank_ui = serialize_question_bank_ui(bank, posts)
    return {
        "slug": slug,
        "bank": bank,
        "posts": posts,
        "question_bank_ui": question_bank_ui,
        "companies": company_options_from_dicts(posts),
        "frequency_report": load_frequency_report(cache_root, slug),
        "meta": meta,
        "paths": {
            "question_bank": str(question_bank_path(cache_root, slug)),
            "frequency_report": str(frequency_report_path(cache_root, slug)),
            "raw_posts": str(raw_posts_path(cache_root, slug)),
        },
    }


def save_bank_artifacts(
    cache_root: Path,
    slug: str,
    posts: list[RawPost],
    ranked: list[Question],
    question_bank: dict,
    frequency_md: str,
) -> None:
    d = bank_dir(cache_root, slug)
    d.mkdir(parents=True, exist_ok=True)
    save_raw_posts(posts, raw_posts_path(cache_root, slug))
    from scripts.corpus.store import save_questions

    save_questions(ranked, questions_path(cache_root, slug))
    question_bank_path(cache_root, slug).write_text(
        json.dumps(question_bank, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    frequency_report_path(cache_root, slug).write_text(frequency_md, encoding="utf-8")
