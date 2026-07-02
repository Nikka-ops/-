"""Lightweight JSON HTTP API + static Web UI for InterviewRadar."""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, unquote

import requests

from scripts.api.uploads import save_resume_base64
from scripts.config import (
    app_display_name,
    banks_dir,
    focus_role_ids,
    full_scrape_recency_days,
    jobs_dir,
    job_recency_days,
    package_root,
    resolve_posts_fallback,
    sample_posts_path,
)
from scripts.jobs.service import (
    catalog_job_sources,
    enrich_job_in_snapshot,
    fetch_jobs,
    fetch_jobs_multi,
    get_job_snapshot,
    list_job_snapshots,
)
from scripts.jobs.service import JobFetchConfig as JobsFetchConfig
from scripts.corpus.bank_cache import list_banks, load_bank_bundle, load_merged_role_bundle
from scripts.corpus.company_catalog import list_company_groups
from scripts.corpus.tech_roles import (
    canonical_role_id,
    get_tech_role,
    list_focus_tech_roles,
    parse_role_ids,
    resolve_role_label,
)
from scripts.config import focus_role_ids
from scripts.service import RunConfig, run_pipeline

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_SAMPLE = sample_posts_path()

_IMAGE_PROXY_HOSTS = (
    "uploadfiles.nowcoder.com",
    "nowcoder.com",
    "xhscdn.com",          # covers sns-webpic-qc.xhscdn.com, sns-img-qc.xhscdn.com, etc.
    "xiaohongshu.com",     # covers ci.xiaohongshu.com and other XHS CDN origins
)


def _proxy_image_response(handler: BaseHTTPRequestHandler, parsed) -> None:
    url = parse_qs(parsed.query).get("url", [""])[0]
    if not url or not url.startswith("http"):
        _json_response(handler, 400, {"error": "invalid_url"})
        return
    host = urlparse(url).netloc.lower()
    if not any(host == h or host.endswith(f".{h}") for h in _IMAGE_PROXY_HOSTS):
        _json_response(handler, 403, {"error": "host_not_allowed"})
        return
    referer = "https://www.nowcoder.com/" if "nowcoder.com" in host else "https://www.xiaohongshu.com/"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": referer,
            },
            timeout=15,
        )
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        _file_response(handler, 200, resp.content, ctype)
    except Exception:  # noqa: BLE001
        # CDN URL may have expired — return 404 so frontend can show fallback
        _json_response(handler, 404, {"error": "image_unavailable"})


def _resolve_local_asset_file(path_str: str) -> Path | None:
    """Resolve a path under corpus_cache/assets for safe local serving."""
    from scripts.config import package_root

    raw = (path_str or "").strip()
    if not raw or "\0" in raw:
        return None
    candidates: list[Path] = []
    p = Path(raw).expanduser()
    if p.is_file():
        candidates.append(p.resolve())
    for base in (Path.cwd(), package_root()):
        candidate = (base / raw).resolve()
        if candidate.is_file():
            candidates.append(candidate)
    for resolved in candidates:
        for root in (Path.cwd().resolve(), package_root().resolve()):
            for assets_subdir in ("corpus_cache/assets", "corpus_cache/xhs/assets"):
                assets_root = (root / assets_subdir).resolve()
                if not assets_root.is_dir():
                    continue
                try:
                    resolved.relative_to(assets_root)
                except ValueError:
                    continue
                return resolved
    return None


def _local_asset_response(handler: BaseHTTPRequestHandler, parsed) -> None:
    rel = parse_qs(parsed.query).get("path", [""])[0]
    path = _resolve_local_asset_file(rel)
    if not path:
        _json_response(handler, 404, {"error": "asset_not_found"})
        return
    content = path.read_bytes()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    _file_response(handler, 200, content, ctype)


def _resolve_raw_posts(path: str) -> str:
    if not path:
        return path
    p = Path(path).expanduser()
    if p.is_file():
        return str(p.resolve())
    for base in (Path.cwd(), package_root()):
        candidate = (base / path).resolve()
        if candidate.is_file():
            return str(candidate)
    return path


def _local_corpus_path() -> Path | None:
    return resolve_posts_fallback()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _file_response(handler: BaseHTTPRequestHandler, status: int, content: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length) if length else b"{}"
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _prepare_body(body: dict) -> dict:
    data = dict(body)
    if data.get("resume_base64"):
        filename = str(data.get("resume_filename") or "resume.pdf")
        data["resume_path"] = save_resume_base64(filename, str(data["resume_base64"]))
    return data


def _config_from_body(
    body: dict,
    *,
    require_resume: bool = False,
    default_agent_handoff: bool = True,
) -> RunConfig:
    data = _prepare_body(body)
    resume_text = str(data.get("resume_text") or "")
    resume_path = str(data.get("resume_path") or data.get("resume") or "")
    role = resolve_role_label(
        role_id=str(data.get("role_id") or "") or None,
        role_text=str(data.get("role") or ""),
    )
    if require_resume and not resume_text and not resume_path:
        raise ValueError("resume_text or resume file is required")
    return RunConfig(
        role=role,
        role_id=str(data.get("role_id") or ""),
        companies=list(data.get("companies") or []),
        resume_path=resume_path,
        resume_text=resume_text,
        cache_dir=str(data.get("cache_dir") or "corpus_cache/banks"),
        cache_ttl_days=int(data.get("cache_ttl_days") or 7),
        refresh=bool(data.get("refresh")),
        rebuild_only=bool(data.get("rebuild_only")),
        raw_posts=_resolve_raw_posts(str(data.get("raw_posts") or "")),
        from_report=bool(data.get("from_report")),
        nowcoder_urls=list(data.get("nowcoder_urls") or []),
        discover_nowcoder=bool(data.get("discover_nowcoder", False)),
        discover_max_per_query=int(data.get("discover_max_per_query") or 50),
        xhs_live=bool(data.get("xhs_live")),
        xhs_use_export=bool(data.get("xhs_use_export", True)),
        xhs_deep=bool(data.get("xhs_deep", True)),
        xhs_priority=bool(data.get("xhs_priority", True)),
        keywords=list(data.get("keywords") or []),
        top_n=int(data.get("top_n") or 30),
        no_semantic_merge=bool(data.get("no_semantic_merge")),
        merge_threshold=float(data.get("merge_threshold") or 0.72),
        filter_company_questions=bool(data.get("filter_company_questions")),
        prep_mode=str(data.get("prep_mode") or "agent"),
        agent_handoff=bool(data.get("agent_handoff", default_agent_handoff)),
        recency_window_days=int(data.get("recency_window_days") or 90),
    )


def _local_report_status() -> dict:
    path = _local_corpus_path()
    if not path:
        return {
            "local_report": None,
            "local_post_count": 0,
            "sample_posts": str(DEFAULT_SAMPLE) if DEFAULT_SAMPLE.is_file() else None,
            "recency_window_days": full_scrape_recency_days(),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = len(data.get("posts", [])) if isinstance(data, dict) else len(data)
    except json.JSONDecodeError:
        count = 0
    sample = DEFAULT_SAMPLE
    sample_count = 0
    if sample.is_file():
        try:
            sd = json.loads(sample.read_text(encoding="utf-8"))
            sample_count = len(sd.get("posts", [])) if isinstance(sd, dict) else len(sd)
        except json.JSONDecodeError:
            sample_count = 0
    return {
        "local_report": str(path),
        "local_post_count": count,
        "sample_posts": str(DEFAULT_SAMPLE) if DEFAULT_SAMPLE.is_file() else None,
        "sample_post_count": sample_count,
        "recency_window_days": full_scrape_recency_days(),
    }


def _resolve_static(route: str) -> Path | None:
    if route in {"/", "/index.html"}:
        return STATIC_DIR / "index.html"
    if route.startswith("/static/"):
        rel = route[len("/static/") :]
        if not rel or ".." in rel:
            return None
        candidate = STATIC_DIR / rel
        try:
            candidate.resolve().relative_to(STATIC_DIR.resolve())
        except ValueError:
            return None
        if candidate.is_file():
            return candidate
    return None


def handle_request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    route = urlparse(path).path

    if method == "GET" and route in {"/health", "/api/health"}:
        return 200, {"status": "ok", "service": app_display_name()}

    if method == "GET" and route == "/api/status":
        payload = {"status": "ok", "service": app_display_name()}
        payload.update(_local_report_status())
        return 200, payload

    if method == "GET" and route == "/api/roles":
        ids = focus_role_ids()
        return 200, {
            "roles": list_focus_tech_roles(),
            "default_role_id": ids[0] if ids else "data",
            "focus_role_ids": ids,
        }

    if method == "GET" and route == "/api/xhs/status":
        from scripts.scrape.xhs_export import xhs_scrape_status

        return 200, xhs_scrape_status()

    if method == "GET" and route == "/api/daily/status":
        from scripts.scrape.schedule_info import daily_schedule_status

        return 200, daily_schedule_status()

    if method == "GET" and route == "/api/scrape/diagnose":
        from scripts.tools.scrape_diagnose import diagnose

        diag_qs = parse_qs(urlparse(path).query)
        role_id = (diag_qs.get("role_id") or [focus_role_ids()[0]])[0]
        companies = (diag_qs.get("companies") or ["all"])[0]
        return 200, diagnose(str(role_id), str(companies))

    if method == "GET" and route == "/api/companies":
        return 200, {"groups": list_company_groups()}

    if method == "GET" and route == "/api/banks":
        cache_root = banks_dir()
        return 200, {"banks": list_banks(cache_root), "cache_dir": str(cache_root)}

    if method == "GET" and route.startswith("/api/role-bundle/"):
        role_id = canonical_role_id(unquote(route[len("/api/role-bundle/") :].strip("/")))
        if not role_id:
            return 400, {"error": "role_id_required"}
        preset = get_tech_role(role_id)
        if preset is None:
            return 404, {"error": "role_not_found", "role_id": role_id}
        parsed = urlparse(path)
        companies_raw = parse_qs(parsed.query).get("companies", [""])[0]
        companies = [c.strip() for c in companies_raw.replace("，", ",").split(",") if c.strip()]
        bundle = load_merged_role_bundle(
            banks_dir(),
            preset.search_as,
            companies=companies or None,
            role_id=role_id,
        )
        if bundle is None:
            return 404, {"error": "no_banks_for_role", "role_id": role_id}
        return 200, bundle

    if method == "GET" and route.startswith("/api/banks/"):
        slug = unquote(route[len("/api/banks/") :].strip("/"))
        if not slug or "/" in slug:
            return 400, {"error": "invalid_slug"}
        bundle = load_bank_bundle(banks_dir(), slug)
        if bundle is None:
            return 404, {"error": "bank_not_found", "slug": slug}
        return 200, bundle

    if method == "GET" and route == "/api/jobs/sources":
        return 200, {"sources": catalog_job_sources()}

    if method == "GET" and route == "/api/jobs/tech-stack":
        from scripts.jobs.tech_stack import analyse_tech_stack
        cache_root = jobs_dir()
        snaps = list_job_snapshots(cache_root)
        # collect jobs from latest data + ai_app snapshots
        all_jobs: list[dict] = []
        loaded: set[str] = set()
        for role_id in ("data", "ai_app"):
            for s in snaps:
                if s.get("role_id") == role_id and s.get("slug") not in loaded:
                    bundle = get_job_snapshot(cache_root, s["slug"])
                    if bundle:
                        all_jobs.extend(bundle.get("jobs") or [])
                        loaded.add(s["slug"])
                    break
        result = analyse_tech_stack(all_jobs)
        return 200, result

    if method == "GET" and route == "/api/jobs":
        cache_root = jobs_dir()
        return 200, {"snapshots": list_job_snapshots(cache_root), "cache_dir": str(cache_root)}

    if method == "GET" and route.startswith("/api/jobs/"):
        slug = unquote(route[len("/api/jobs/") :].strip("/"))
        if not slug or "/" in slug or slug in ("sources", "tech-stack"):
            return 400, {"error": "invalid_slug"}
        bundle = get_job_snapshot(jobs_dir(), slug)
        if bundle is None:
            return 404, {"error": "snapshot_not_found", "slug": slug}
        return 200, bundle

    if method != "POST":
        return 405, {"error": "method_not_allowed"}

    if route == "/api/bank":
        if not body or not body.get("role"):
            return 400, {"error": "role is required"}
        config = _config_from_body(body, default_agent_handoff=False)
        result = run_pipeline(config)
        payload = result.to_dict()
        bundle = load_bank_bundle(Path(config.cache_dir), result.slug)
        if bundle:
            payload["posts"] = bundle.get("posts", [])
            payload["companies"] = bundle.get("companies", [])
            payload["frequency_report"] = bundle.get("frequency_report", "")
        return 200, payload

    if route == "/api/predict":
        if not body or not body.get("role"):
            return 400, {"error": "role is required"}
        try:
            data = dict(body or {})
            data.setdefault("prep_mode", "agent")
            data.setdefault("agent_handoff", True)
            config = _config_from_body(data, require_resume=True)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        result = run_pipeline(config)
        return 200, result.to_dict()

    if route == "/api/handoff":
        if not body or not body.get("role"):
            return 400, {"error": "role is required"}
        data = dict(body or {})
        data["prep_mode"] = "agent"
        data["agent_handoff"] = True
        config = _config_from_body(data)
        result = run_pipeline(config)
        return 200, result.to_dict()

    if route == "/api/prep":
        # Prep Agent 内化：服务端全自动执行步骤 4–8
        if not body or not body.get("role"):
            return 400, {"error": "role is required"}
        from scripts.corpus.prep_agent import build_prep_package
        from scripts.corpus.ai_gate import ai_enabled
        data = dict(body or {})
        role = str(data.get("role") or "数据开发")
        companies = [str(c).strip() for c in (data.get("companies") or []) if str(c).strip()]
        resume_text = str(data.get("resume_text") or "")
        mode = "auto" if ai_enabled() else "heuristic"

        # 加载最新题库
        all_banks = list_banks(banks_dir())
        role_banks = [b for b in all_banks if role in (b.get("role") or "")]
        top_questions = []
        if role_banks:
            bundle = load_bank_bundle(banks_dir(), role_banks[0]["slug"]) or {}
            ui = bundle.get("question_bank_ui") or {}
            top_questions = (ui.get("questions") or [])[:40]

        from scripts.models import Question
        qs = [Question.from_dict(q) if isinstance(q, dict) else q for q in top_questions]

        pkg = build_prep_package(
            role=role,
            companies=companies,
            top_questions=qs,
            resume_text=resume_text,
            mode=mode,
        )
        return 200, pkg.to_dict()

    if route == "/api/xhs/scrape-safe":
        from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError
        from scripts.scrape.xhs_export import run_safe_xhs_scrape
        from scripts.scrape.xhs_scrape_plan import plan_xhs_scrape_batch

        data = dict(body or {})
        role_id = str(data.get("role_id") or "").strip()
        companies = [str(c).strip() for c in (data.get("companies") or []) if str(c).strip()]
        explicit = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
        keywords, pause, batch_size, plan_meta = plan_xhs_scrape_batch(
            role_id or "data",
            companies,
            explicit_keywords=explicit or None,
            core_only=bool(data.get("core_only", True)),
            aggressive=bool(data.get("aggressive")),
            keywords_per_day=int(data.get("keywords_per_day") or 0),
            rotate=not explicit,
        )
        if not keywords:
            return 400, {"error": "keywords_or_role_id_required"}
        try:
            result = run_safe_xhs_scrape(
                keywords,
                batch_size=batch_size,
                pause_seconds=float(data.get("pause_seconds") or pause),
                limit_keywords=not bool(data.get("core_only", True)) and not explicit,
            )
            result.update(plan_meta)
        except ValueError as exc:
            return 400, {"error": "xhs_config", "message": str(exc)}
        except (SpiderXHSScrapeError, FileNotFoundError) as exc:
            return 502, {"error": "xhs_scrape_failed", "message": str(exc)}
        return 200, result

    if route == "/api/xhs/incremental":
        from scripts.scrape.spider_xhs_driver import SpiderXHSScrapeError, _HTTP_461_HINT
        from scripts.scrape.xhs_export import (
            collect_xhs_export_files,
            run_safe_xhs_scrape,
        )
        from scripts.scrape.scrape_state import (
            collect_note_ids_from_export_files,
            load_scrape_state,
            register_xhs_note_ids,
            save_scrape_state,
        )
        from scripts.scrape.xhs_scrape_plan import plan_xhs_scrape_batch
        from scripts.config import xhs_export_max_age_days

        data = dict(body or {})
        role_id = str(data.get("role_id") or "data").strip()
        companies = [str(c).strip() for c in (data.get("companies") or []) if str(c).strip()]
        import_only = bool(data.get("import_only"))
        out: dict = {"role_id": role_id, "xhs": {}, "classify": {}}

        if not import_only:
            keywords, pause, batch_size, plan_meta = plan_xhs_scrape_batch(
                role_id,
                companies,
                core_only=bool(data.get("core_only", True)),
                aggressive=bool(data.get("aggressive")),
                keywords_per_day=int(data.get("keywords_per_day") or 0),
            )
            out["xhs"]["plan"] = plan_meta
            out["xhs"]["keywords_today"] = keywords
            try:
                scrape = run_safe_xhs_scrape(
                    keywords,
                    batch_size=batch_size,
                    pause_seconds=float(data.get("pause_seconds") or pause),
                    limit_keywords=not bool(data.get("core_only", True)),
                )
                out["xhs"].update(scrape)
            except (SpiderXHSScrapeError, FileNotFoundError, ValueError) as exc:
                msg = str(exc)
                out["xhs"]["error"] = msg
                if "461" not in msg:
                    return 502, {"error": "xhs_scrape_failed", "message": msg, **out}
            state = load_scrape_state()
            paths = collect_xhs_export_files(max_age_days=xhs_export_max_age_days())
            out["xhs"]["note_ids_registered"] = register_xhs_note_ids(
                state,
                collect_note_ids_from_export_files(paths),
            )
            save_scrape_state(state)

        bank_body = dict(data)
        bank_body.setdefault("role_id", role_id)
        bank_body.setdefault("role", resolve_role_label(role_id=role_id))
        bank_body["refresh"] = True
        bank_body["rebuild_only"] = False
        bank_body["xhs_use_export"] = True
        bank_body["xhs_live"] = False
        bank_body["xhs_deep"] = bool(data.get("xhs_deep", True))
        bank_body["xhs_priority"] = bool(data.get("xhs_priority", True))
        bank_body["discover_nowcoder"] = bool(data.get("discover_nowcoder", False))
        try:
            config = _config_from_body(bank_body, default_agent_handoff=False)
            pipeline = run_pipeline(config)
            payload = pipeline.to_dict()
            bundle = load_bank_bundle(Path(config.cache_dir), pipeline.slug)
            if bundle:
                payload["posts"] = bundle.get("posts", [])
                payload["companies"] = bundle.get("companies", [])
            out["classify"] = {
                k: v
                for k, v in (payload.get("sources") or {}).items()
                if k
                in {
                    "input",
                    "kept",
                    "junk_dropped",
                    "xhs_promo_dropped",
                    "xhs_asking_dropped",
                    "xhs_not_recap_dropped",
                    "role_dropped",
                    "role_prefilter_dropped",
                    "ai_dropped",
                    "rule_kept",
                    "xiaohongshu_export",
                    "xhs_role_matched",
                }
                or k.endswith("_dropped")
            }
            out.update(
                {
                    "slug": payload.get("slug"),
                    "post_count": payload.get("post_count"),
                    "question_count": payload.get("question_count"),
                    "ingest_warnings": payload.get("ingest_warnings"),
                    "posts": payload.get("posts"),
                    "companies": payload.get("companies"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return 500, {"error": "bank_build_failed", "message": str(exc), **out}

        if out.get("post_count"):
            return 200, out
        if import_only and out.get("xhs", {}).get("error"):
            return 200, out
        err = (out.get("xhs") or {}).get("error", "")
        if "461" in err:
            return 502, {"error": "xhs_blocked", "message": _HTTP_461_HINT, **out}
        return 200, out

    if route == "/api/jobs/fetch":
        data = dict(body or {})
        role = str(data.get("role") or "")
        role_id = str(data.get("role_id") or "")
        raw_role_ids = data.get("role_ids")
        if isinstance(raw_role_ids, list):
            role_ids = [
                canonical_role_id(str(r).strip())
                for r in raw_role_ids
                if str(r).strip()
            ]
        else:
            role_ids = parse_role_ids(role_id, str(data.get("role_ids_csv") or ""))
        if not role and not role_ids:
            role_ids = focus_role_ids()
        if not role and not role_ids:
            return 400, {"error": "role or role_id is required"}
        job_config = JobsFetchConfig(
            role=role,
            role_id=role_ids[0] if len(role_ids) == 1 else "",
            companies=list(data.get("companies") or []),
            cities=list(data.get("cities") or []),
            sources=list(data.get("sources") or []),
            keywords=list(data.get("keywords") or []),
            max_per_query=int(data.get("max_per_query") or 100),
            include_aggregators=not bool(data.get("no_boss")),
            use_job_pro=not bool(data.get("no_job_pro")),
            job_pro_scope=str(data.get("job_pro_scope") or "social"),
            job_pro_details=bool(data.get("job_pro_details", True)),
            boss_cdp=bool(data.get("boss_cdp")),
            skip_interview_discover=bool(data.get("skip_interview_discover", True)),
            cache_dir=str(data.get("cache_dir") or jobs_dir()),
            job_recency_days=int(data.get("job_recency_days") or 0),
        )
        result = fetch_jobs_multi(job_config, role_ids, job_config.cache_dir or jobs_dir())
        return 200, result.to_dict()

    if route == "/api/jobs/enrich":
        job = body.get("job") if body else None
        if not job or not isinstance(job, dict):
            return 400, {"error": "job is required"}
        slug = str((body or {}).get("slug") or "").strip()
        result = enrich_job_in_snapshot(
            str((body or {}).get("cache_dir") or jobs_dir()),
            slug,
            job,
        )
        return 200, result

    return 404, {"error": "not_found", "path": route}


class InterviewRadarHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/proxy-image":
            _proxy_image_response(self, parsed)
            return
        if parsed.path == "/api/local-asset":
            _local_asset_response(self, parsed)
            return
        static = _resolve_static(parsed.path)
        if static:
            content = static.read_bytes()
            if static.name == "index.html":
                label = app_display_name()
                text = content.decode("utf-8").replace("data_agent_adar", label)
                content = text.encode("utf-8")
            ctype = mimetypes.guess_type(static.name)[0] or "application/octet-stream"
            _file_response(self, 200, content, ctype)
            return
        try:
            status, payload = handle_request("GET", self.path)
            _json_response(self, status, payload)
        except Exception as exc:  # noqa: BLE001
            _json_response(self, 500, {"error": "internal_error", "message": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = _read_json(self)
            status, payload = handle_request("POST", self.path, body)
            _json_response(self, status, payload)
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid_json"})
        except FileNotFoundError as exc:
            _json_response(self, 404, {"error": "not_found", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc()
            _json_response(self, 500, {"error": "internal_error", "message": str(exc)})


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), InterviewRadarHandler)
    print(f"{app_display_name()} Web UI: http://{host}:{port}/")
    print(f"  API health: http://{host}:{port}/health")
    print("  GET  /api/banks | /api/banks/{slug}")
    print("  POST /api/bank | /api/handoff | /api/predict | /api/jobs/fetch")
    print("  GET  /api/jobs | /api/jobs/{slug} | /api/jobs/sources")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="InterviewRadar Web UI + API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
