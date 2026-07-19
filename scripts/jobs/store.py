"""Persist job snapshots under corpus_cache/jobs/."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.jobs.models import JobPosting

_SLUG_SAFE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def _slugify(text: str) -> str:
    cleaned = _SLUG_SAFE.sub("_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "jobs"


def jobs_snapshot_slug(role: str, companies: list[str], cities: list[str]) -> str:
    parts = [_slugify(role)]
    if companies:
        parts.append(_slugify("_".join(sorted(companies))))
    if cities:
        parts.append(_slugify("_".join(sorted(cities))))
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
    return f"{parts[0]}_{digest}"


def write_snapshot(
    root: Path,
    slug: str,
    jobs: list[JobPosting],
    *,
    role: str,
    role_id: str = "",
    companies: list[str],
    cities: list[str],
    sources: dict[str, dict],
    queries: list[str],
) -> dict[str, str]:
    snap_dir = root / slug
    snap_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    jobs_path = snap_dir / "jobs.json"
    meta_path = snap_dir / "meta.json"

    # Guard: never let an empty/collapsed scrape (risk-control, network hiccup)
    # overwrite a healthy snapshot. A near-empty result replacing a populated one
    # is almost always a failed fetch, not "the market emptied out".
    prior_count = len(_load_prior_ids(jobs_path if jobs_path.is_file() else None))
    if not jobs and prior_count > 0:
        raise ValueError(
            f"refusing to overwrite {slug}: fetched 0 jobs but snapshot has {prior_count} "
            "(likely a failed fetch / risk-control); keeping existing data"
        )

    prior_ids = _load_prior_ids(jobs_path if jobs_path.is_file() else None)
    for job in jobs:
        fp = job.fingerprint()
        job.is_new = fp not in prior_ids

    jobs_payload = [j.to_dict() for j in jobs]
    jobs_path.write_text(json.dumps(jobs_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "slug": slug,
        "role": role,
        "role_id": role_id,
        "companies": companies,
        "cities": cities,
        "queries": queries,
        "fetched_at": fetched_at,
        "job_count": len(jobs),
        "new_count": sum(1 for j in jobs if j.is_new),
        "open_count": sum(1 for j in jobs if j.status == "open"),
        "sources": sources,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "slug": slug,
        "jobs": str(jobs_path),
        "meta": str(meta_path),
        "fetched_at": fetched_at,
    }


def _load_prior_ids(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    ids: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            source = item.get("source") or ""
            source_id = item.get("source_id") or ""
            if source and source_id:
                ids.add(f"{source}:{source_id}")
    return ids


def list_snapshots(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        meta_path = child / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        # 只返回目录名与 slug 一致的快照（防止 GBK/UTF-8 乱码目录混入）
        slug_in_meta = str(meta.get("slug") or "").strip()
        if slug_in_meta and child.name != slug_in_meta:
            continue
        rows.append(meta)
    rows.sort(key=lambda m: m.get("fetched_at") or "", reverse=True)
    return rows


def load_snapshot(root: Path, slug: str) -> dict | None:
    snap_dir = root / slug
    jobs_path = snap_dir / "jobs.json"
    meta_path = snap_dir / "meta.json"
    if not jobs_path.is_file() or not meta_path.is_file():
        return None
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {"meta": meta, "jobs": jobs}


def patch_job_description(
    root: Path,
    slug: str,
    source: str,
    source_id: str,
    description: str,
) -> bool:
    """Update one job's description in an existing snapshot."""
    snap_dir = root / slug
    jobs_path = snap_dir / "jobs.json"
    if not jobs_path.is_file():
        return False
    try:
        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    updated = False
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if item.get("source") == source and item.get("source_id") == source_id:
            item["description"] = description
            updated = True
            break
    if not updated:
        return False
    jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
