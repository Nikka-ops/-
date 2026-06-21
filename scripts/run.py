#!/usr/bin/env python3
"""Unified InterviewRadar runner — thin CLI over scripts.service."""
from __future__ import annotations

import argparse
import json

from scripts.service import RunConfig, run_pipeline


from scripts.corpus.tech_roles import resolve_role_label


def _config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        role=resolve_role_label(getattr(args, "role_id", "") or None, args.role),
        companies=args.companies,
        resume_path=args.resume,
        resume_text=args.resume_text,
        cache_dir=args.cache_dir,
        cache_ttl_days=args.cache_ttl_days,
        refresh=args.refresh,
        rebuild_only=args.rebuild_only,
        raw_posts=args.raw_posts,
        from_report=args.from_report,
        nowcoder_urls=args.nowcoder_urls,
        discover_nowcoder=args.discover_nowcoder,
        discover_max_per_query=args.discover_max,
        xhs_live=args.xhs_live,
        xhs_deep=args.xhs_deep,
        keywords=args.keywords,
        top_n=args.top_n,
        no_semantic_merge=args.no_semantic_merge,
        merge_threshold=args.merge_threshold,
        filter_company_questions=args.filter_company_questions,
        prep_mode=args.prep_mode,
        agent_handoff=not (args.no_agent_handoff or args.bank_only),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InterviewRadar unified runner")
    parser.add_argument("--role", default="", help="Target role text (or use --role-id)")
    parser.add_argument(
        "--role-id",
        default="",
        help="Preset role: backend, algorithm, llm, agent, ai_app, data, qa, …",
    )
    parser.add_argument("--resume", default="", help="Resume path (optional)")
    parser.add_argument("--companies", nargs="*", default=[], help="Target companies")
    parser.add_argument("--cache-dir", default="corpus_cache/banks")
    parser.add_argument("--cache-ttl-days", type=int, default=7)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--raw-posts", default="")
    parser.add_argument("--from-report", action="store_true")
    parser.add_argument("--nowcoder-urls", nargs="*", default=[])
    parser.add_argument("--discover-nowcoder", action="store_true", help="Auto-discover 牛客 discuss URLs")
    parser.add_argument("--discover-max", type=int, default=50, help="Max posts/URLs per search query")
    parser.add_argument("--xhs-live", action="store_true")
    parser.add_argument("--xhs-deep", action="store_true")
    parser.add_argument("--keywords", nargs="*", default=[])
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--rebuild-only", action="store_true")
    parser.add_argument("--no-semantic-merge", action="store_true")
    parser.add_argument("--merge-threshold", type=float, default=0.72)
    parser.add_argument("--filter-company-questions", action="store_true")
    parser.add_argument("--resume-text", default="")
    parser.add_argument(
        "--prep-mode",
        choices=("agent", "heuristic"),
        default="agent",
        help="agent=生成交接包(默认,对齐原设计); heuristic=规则预览(非正式备考包)",
    )
    parser.add_argument("--no-agent-handoff", action="store_true")
    parser.add_argument(
        "--bank-only",
        action="store_true",
        help="只生成题库(等同 --no-agent-handoff)",
    )
    parser.add_argument("--json", action="store_true", help="Print RunResult JSON to stdout")
    args = parser.parse_args(argv)

    result = run_pipeline(_config_from_args(args))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            f"Question bank: {result.paths['question_bank']} "
            f"({result.ranked_count} questions from {result.post_count} posts)"
        )
        if result.paths.get("agent_handoff"):
            print(f"Agent handoff: {result.paths['agent_handoff']} (prep_mode={result.prep_mode})")
        for w in result.resume_warnings:
            print(f"Note: {w}")
        if result.prep_mode == "agent":
            print("Next: 在 Cursor 中让 Agent 读取 agent_handoff.md,按 SKILL.md 步骤 4–8 撰写 prep_package.md")
        if result.predicted:
            print(f"Heuristic preview: {result.paths.get('prep_package')}")
        elif args.resume or args.resume_text:
            if result.prep_mode == "agent":
                print("个性化备考包由 Agent 生成,非本命令直接输出。")
        else:
            print("Tip: 加 --resume 或 --resume-text 以在交接包中包含简历上下文")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
