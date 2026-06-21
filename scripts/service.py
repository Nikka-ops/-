"""Core InterviewRadar pipeline (CLI + HTTP API)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from scripts.agent_handoff import build_agent_context, write_agent_handoff
from scripts.corpus.ingest_fallback import (
    build_ingest_failure_message,
    ingest_attempted_live,
    nonempty_posts,
    resolve_role_aware_fallback,
    role_mismatch_warning,
)
from scripts.config import cache_dir
from scripts.connectors.nowcoder import NowCoderConnector
from scripts.connectors.xiaohongshu import XiaohongshuConnector
from scripts.corpus.bank_cache import (
    bank_slug,
    frequency_report_path,
    is_fresh,
    load_cached_raw_posts,
    predicted_path,
    prep_package_path,
    question_bank_path,
    save_bank_artifacts,
    write_meta,
)
from scripts.corpus.classify import classify_search_queries
from scripts.corpus.role_match import annotate_post, filter_posts_for_bank
from scripts.corpus.export_bank import build_question_bank, render_frequency_report
from scripts.corpus.pipeline import build_ranked_questions
from scripts.corpus.personalize import (
    build_followup_chains,
    gap_rows,
    predict_questions,
    render_prep_package,
)
from scripts.corpus.post_dedupe import dedupe_raw_posts
from scripts.corpus.post_supplement import supplement_posts_for_role
from scripts.corpus.recency import RECENCY_WINDOW_DAYS, filter_recent
from scripts.corpus.store import load_raw_posts
from scripts.discover.nowcoder_urls import discover_nowcoder_urls
from scripts.discover.nowcoder_moments import search_nowcoder_moments
from scripts.models import RawPost
from scripts.ocr.post_images import enrich_posts_image_ocr
from scripts.resume_extract import ResumeExtraction, extract_resume
from scripts.scrape.mediacrawler_driver import MediaCrawlerDriver, MediaCrawlerScrapeError
from scripts.scrape.xhs_export import load_xhs_posts_from_exports


@dataclass
class RunConfig:
    role: str
    role_id: str = ""
    companies: list[str] = field(default_factory=list)
    resume_path: str = ""
    resume_text: str = ""
    cache_dir: str = "corpus_cache/banks"
    cache_ttl_days: int = 7
    refresh: bool = False
    rebuild_only: bool = False
    raw_posts: str = ""
    from_report: bool = False
    nowcoder_urls: list[str] = field(default_factory=list)
    discover_nowcoder: bool = False
    discover_max_per_query: int = 50
    discover_max_pages: int = 30
    recency_window_days: int = 90
    skip_role_filter: bool = False
    xhs_live: bool = False
    xhs_use_export: bool = True
    xhs_deep: bool = True
    xhs_priority: bool = True
    xhs_min_posts_skip_nowcoder: int = 5
    keywords: list[str] = field(default_factory=list)
    top_n: int = 30
    no_semantic_merge: bool = False
    merge_threshold: float = 0.72
    filter_company_questions: bool = False
    prep_mode: str = "agent"  # agent: handoff for LLM/vision | heuristic: rule-based preview only
    agent_handoff: bool = True


@dataclass
class RunResult:
    slug: str
    bank: dict
    ranked_count: int
    post_count: int
    paths: dict
    ingest_mode: str
    sources: dict
    predicted: list[dict] | None = None
    followup_chains: list[dict] | None = None
    resume_warnings: list[str] = field(default_factory=list)
    ingest_warnings: list[str] = field(default_factory=list)
    agent_handoff: dict | None = None
    prep_mode: str = "agent"

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "ingest_mode": self.ingest_mode,
            "prep_mode": self.prep_mode,
            "sources": self.sources,
            "post_count": self.post_count,
            "question_count": self.ranked_count,
            "paths": self.paths,
            "bank": self.bank,
            "predicted": self.predicted,
            "followup_chains": self.followup_chains,
            "resume_warnings": self.resume_warnings,
            "ingest_warnings": self.ingest_warnings,
            "agent_handoff": self.agent_handoff,
        }


def _load_posts_from_report(path: Path) -> list[RawPost]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [RawPost.from_dict(d) for d in data]
    if isinstance(data, dict) and "posts" in data:
        return [RawPost.from_dict(d) for d in data["posts"]]
    raise ValueError(f"Unrecognized report format: {path}")


def ingest_posts(config: RunConfig, queries: list[str]) -> tuple[list[RawPost], dict, str]:
    slug = bank_slug(config.role, config.companies)
    cache_root = Path(config.cache_dir)

    if config.rebuild_only:
        cached = load_cached_raw_posts(cache_root, slug)
        if not cached:
            raise FileNotFoundError(f"No cached raw_posts for slug {slug}")
        cached = [annotate_post(p) for p in cached]
        cached = enrich_posts_image_ocr(cached)
        return cached, {"mode": "rebuild"}, slug

    if not config.refresh and is_fresh(cache_root, slug, config.cache_ttl_days, today=date.today()):
        cached = load_cached_raw_posts(cache_root, slug)
        if cached:
            return cached, {"mode": "cache"}, slug

    sources: dict = {}
    posts: list[RawPost] = []
    ingest_warnings: list[str] = []
    xhs_loaded_count = 0

    explicit_raw = bool(config.raw_posts)
    if explicit_raw:
        raw_path = Path(config.raw_posts)
        if config.from_report or (raw_path.suffix == ".json" and "report" in raw_path.name):
            posts = _load_posts_from_report(raw_path)
        else:
            posts = load_raw_posts(raw_path)
        sources["raw_posts"] = str(raw_path)
        mismatch = role_mismatch_warning(config.role, raw_path)
        if mismatch:
            sources["role_mismatch_warning"] = mismatch
            ingest_warnings.append(mismatch)

    if config.xhs_use_export:
        from scripts.config import xhs_export_max_age_days, xhs_export_max_files

        export_posts, xhs_export_meta = load_xhs_posts_from_exports(
            enable_ocr=config.xhs_deep,
            max_age_days=xhs_export_max_age_days(),
            max_files=xhs_export_max_files(),
        )
        sources["xiaohongshu_export"] = xhs_export_meta
        if export_posts:
            posts.extend(export_posts)
            xhs_loaded_count = len(export_posts)
        elif xhs_export_meta.get("status") == "missing" and config.xhs_priority:
            ingest_warnings.append(
                "小红书本地导出为空 — 先运行: uv run python -m scripts.tools.xhs_scrape_safe --role-id ai_app"
            )

    rolling_nc = cache_dir() / "daily" / "rolling_nowcoder_posts.json"
    if rolling_nc.is_file() and not config.rebuild_only:
        try:
            rolling_posts = load_raw_posts(rolling_nc)
            if rolling_posts:
                posts.extend(rolling_posts)
                sources["daily_nowcoder_roll"] = {
                    "path": str(rolling_nc),
                    "count": len(rolling_posts),
                }
        except (OSError, ValueError, json.JSONDecodeError):
            ingest_warnings.append(f"无法读取每日牛客累积文件: {rolling_nc}")

    nowcoder_urls = list(config.nowcoder_urls)
    discover_live = config.discover_nowcoder and not explicit_raw and not config.rebuild_only
    if (
        config.xhs_priority
        and xhs_loaded_count >= config.xhs_min_posts_skip_nowcoder
        and discover_live
    ):
        discover_live = False
        sources["nowcoder_skipped"] = {
            "reason": "xhs_priority",
            "xhs_posts": xhs_loaded_count,
        }

    if discover_live:
        discovered, discover_meta = discover_nowcoder_urls(
            queries,
            max_per_query=config.discover_max_per_query,
        )
        sources["nowcoder_discover"] = discover_meta
        sources["nowcoder_discover"]["urls"] = discovered
        for url in discovered:
            if url not in nowcoder_urls:
                nowcoder_urls.append(url)
        moment_posts, moment_meta = search_nowcoder_moments(
            queries,
            max_per_query=config.discover_max_per_query,
            max_pages=max(5, config.discover_max_pages),
        )
        sources["nowcoder_moments"] = moment_meta
        posts.extend(moment_posts)

    if nowcoder_urls:
        nc = NowCoderConnector(post_urls=nowcoder_urls).search(queries)
        sources["nowcoder"] = {
            "status": nc.status,
            "message": nc.message,
            "count": len(nc.posts),
            "urls": nowcoder_urls,
        }
        posts.extend(nc.posts)

    if config.xhs_live:
        try:
            driver = MediaCrawlerDriver()
            keywords = queries[:6]
            export = driver.scrape_xhs(
                keywords,
                login_type="cookie",
                max_keywords_per_batch=2,
                batch_pause_seconds=45.0,
            )
            xhs = XiaohongshuConnector(
                export_path=str(export),
                enable_image_ocr=config.xhs_deep,
            )
            live_result = xhs.search([])
            sources["xiaohongshu_live"] = {
                "status": live_result.status,
                "message": live_result.message,
                "export": str(export),
                "keywords": keywords,
                "ocr_mode": "deep" if config.xhs_deep else "fast",
            }
            posts.extend(live_result.posts)
        except (MediaCrawlerScrapeError, FileNotFoundError, ValueError) as exc:
            sources["xiaohongshu_live"] = {"status": "degraded", "message": str(exc)}

    supplement_meta: dict = {}
    if not config.rebuild_only and (
        ingest_attempted_live(config)
        or discover_live
        or xhs_loaded_count > 0
    ):
        posts, supplement_meta = supplement_posts_for_role(
            posts,
            config.role,
            config.role_id or "",
            cache_root,
        )
        if supplement_meta.get("from_banks") or supplement_meta.get("from_files"):
            sources["post_supplement"] = supplement_meta

    posts = dedupe_raw_posts(posts)
    posts = nonempty_posts(posts)
    posts = [annotate_post(p) for p in posts]
    posts = enrich_posts_image_ocr(posts)
    from scripts.corpus.post_ai_filter import filter_interview_experience_posts_hybrid

    posts, non_interview_dropped, filter_meta = filter_interview_experience_posts_hybrid(posts)
    if non_interview_dropped:
        sources["non_interview_dropped"] = len(non_interview_dropped)
    if filter_meta.get("ai_enabled"):
        sources["post_ai_filter"] = {
            k: filter_meta[k]
            for k in (
                "rule_keep",
                "rule_drop",
                "ai_review",
                "ai_keep",
                "ai_drop",
                "ai_cache_hits",
                "ai_errors",
            )
            if k in filter_meta
        }
    kept, dropped = filter_posts_for_bank(posts, config.role)
    if config.skip_role_filter:
        kept, dropped = posts, []
    elif dropped:
        sources["role_filter_dropped"] = len(dropped)

    posts = kept

    if not posts:
        if ingest_attempted_live(config):
            raise FileNotFoundError(build_ingest_failure_message(config.role, config, queries))
        if explicit_raw:
            raise FileNotFoundError(
                f"语料文件无有效正文或为空：{config.raw_posts}。"
                "请检查路径、格式，或换用与岗位「{config.role}」匹配的 JSON。"
            )
        fallback_path = resolve_role_aware_fallback(config.role)
        if fallback_path:
            posts = _load_posts_from_report(fallback_path)
            sources["fallback"] = str(fallback_path)
            sources["fallback_reason"] = "role_matched_local_corpus"
        else:
            raise FileNotFoundError(build_ingest_failure_message(config.role, config, queries))

    window = config.recency_window_days if config.recency_window_days > 0 else RECENCY_WINDOW_DAYS
    posts = filter_recent(posts, window_days=window, today=date.today())
    if not posts:
        raise FileNotFoundError(
            f"语料在近 {window} 天内无有效帖。"
            "可加大语料、调大 FULL_SCRAPE_RECENCY_DAYS 或 --refresh 重新抓取。"
        )
    return posts, {"mode": "ingest", "sources": sources, "warnings": ingest_warnings}, slug


def build_bank_from_posts(
    config: RunConfig,
    posts: list[RawPost],
    sources_meta: dict,
) -> tuple[dict, list]:
    companies_filter = config.companies if config.filter_company_questions else None
    ranked = build_ranked_questions(
        posts,
        today=date.today(),
        semantic_merge=not config.no_semantic_merge,
        merge_threshold=config.merge_threshold,
        companies_filter=companies_filter,
    )
    window = (
        config.recency_window_days
        if config.recency_window_days > 0
        else RECENCY_WINDOW_DAYS
    )
    bank = build_question_bank(
        role=config.role,
        companies=config.companies,
        ranked=ranked,
        post_count=len(posts),
        sources_meta=sources_meta,
        recency_window_days=window,
    )
    return bank, ranked


def resolve_resume(config: RunConfig) -> tuple[str, ResumeExtraction | None, list[str]]:
    warnings: list[str] = []
    text = config.resume_text.strip()
    extraction: ResumeExtraction | None = None
    if config.resume_path:
        extraction = extract_resume(config.resume_path, try_ocr=not text)
        if not text:
            text = extraction.text
        if extraction.needs_vision and not text:
            warnings.append(
                "Resume needs vision parsing (Agent step 1). "
                "See agent_handoff.md for asset_path."
            )
        elif extraction.ocr_used:
            warnings.append(f"Resume OCR confidence={extraction.ocr_confidence:.2f}")
    return text, extraction, warnings


def run_pipeline(config: RunConfig) -> RunResult:
    queries = classify_search_queries(
        roles=[config.role],
        companies=config.companies or None,
        role_id=config.role_id or None,
    )
    posts, ingest_meta, slug = ingest_posts(config, queries)
    ingest_warnings = list(ingest_meta.get("warnings") or [])
    if ingest_meta.get("sources", {}).get("role_mismatch_warning"):
        w = ingest_meta["sources"]["role_mismatch_warning"]
        if w not in ingest_warnings:
            ingest_warnings.append(w)
    cache_root = Path(config.cache_dir)

    meta_file = cache_root / slug / "meta.json"
    if meta_file.is_file() and ingest_meta.get("mode") in {"cache", "rebuild"}:
        sources_meta = json.loads(meta_file.read_text(encoding="utf-8")).get("sources", {})
    else:
        sources_meta = ingest_meta.get("sources", {"ingest": ingest_meta.get("mode")})

    bank, ranked = build_bank_from_posts(config, posts, sources_meta)
    report_md = render_frequency_report(bank, top_n=config.top_n)
    save_bank_artifacts(cache_root, slug, posts, ranked, bank, report_md)
    write_meta(
        cache_root,
        slug,
        role=config.role,
        role_id=config.role_id,
        companies=config.companies,
        post_count=len(posts),
        question_count=len(ranked),
        sources=sources_meta,
    )

    paths = {
        "question_bank": str(question_bank_path(cache_root, slug)),
        "frequency_report": str(frequency_report_path(cache_root, slug)),
    }

    resume_text, resume_extraction, warnings = resolve_resume(config)
    predicted = None
    chains_out = None
    handoff_ctx = None

    if config.agent_handoff:
        handoff_ctx = build_agent_context(
            role=config.role,
            companies=config.companies,
            posts=posts,
            ranked=ranked,
            bank=bank,
            paths=dict(paths),
            resume=resume_extraction,
            resume_text=resume_text,
            ingest_mode=ingest_meta.get("mode", "ingest"),
            sources=sources_meta,
        )
        md_path, json_path = write_agent_handoff(cache_root, slug, handoff_ctx)
        paths["agent_handoff"] = str(md_path)
        paths["agent_context"] = str(json_path)

    if config.prep_mode == "heuristic" and resume_text:
        predicted = predict_questions(ranked, resume_text, role=config.role, top_n=config.top_n)
        chains = build_followup_chains(predicted, resume_text)
        gaps = gap_rows(resume_text, config.role, ranked)
        prep_md = render_prep_package(
            role=config.role,
            resume_text=resume_text,
            bank=bank,
            predicted=predicted,
            chains=chains,
            gaps=gaps,
        )
        pred_p = predicted_path(cache_root, slug)
        prep_p = prep_package_path(cache_root, slug)
        pred_p.write_text(json.dumps(predicted, ensure_ascii=False, indent=2), encoding="utf-8")
        prep_p.write_text(prep_md, encoding="utf-8")
        paths["predicted_questions"] = str(pred_p)
        paths["prep_package"] = str(prep_p)
        chains_out = [c.to_dict() for c in chains]
        warnings.append(
            "prep_mode=heuristic: 规则预览已生成,非 Agent 备考包。"
            "正式输出请让 Agent 读取 agent_handoff.md 并按 SKILL.md 撰写。"
        )

    return RunResult(
        slug=slug,
        bank=bank,
        ranked_count=len(ranked),
        post_count=len(posts),
        paths=paths,
        ingest_mode=ingest_meta.get("mode", "ingest"),
        sources=sources_meta,
        predicted=predicted,
        followup_chains=chains_out,
        resume_warnings=warnings,
        ingest_warnings=ingest_warnings,
        agent_handoff=handoff_ctx,
        prep_mode=config.prep_mode,
    )
