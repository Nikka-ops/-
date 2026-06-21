"""Build question_bank.json and frequency_report.md from ranked questions."""
from __future__ import annotations

from datetime import date

from scripts.corpus.clusters import assign_cluster_ids, build_clusters
from scripts.corpus.dedupe_rank import _recency_weight
from scripts.corpus.group import group_questions_by_taxonomy
from scripts.models import Question


def _confidence(freq: int) -> str:
    if freq >= 3:
        return "高频"
    if freq == 2:
        return "中频"
    return "低频"


def build_question_bank(
    *,
    role: str,
    companies: list[str],
    ranked: list[Question],
    post_count: int,
    sources_meta: dict,
    generated_at: date | None = None,
    recency_window_days: int = 90,
) -> dict:
    ref = generated_at or date.today()
    taxonomy_rows: list[dict] = []
    grouped = group_questions_by_taxonomy(ranked)
    for company, roles in grouped.items():
        for role_label, bucket in roles.items():
            taxonomy_rows.append(
                {
                    "company": company,
                    "role": role_label,
                    "question_count": len(bucket),
                    "top_question": bucket[0].text if bucket else "",
                }
            )
    taxonomy_rows.sort(key=lambda r: (-r["question_count"], r["company"], r["role"]))

    assign_cluster_ids(ranked)

    def score_fn(q: Question) -> float:
        return q.freq * _recency_weight(q.latest_posted_at, ref)

    clusters = build_clusters(ranked, ref_score_fn=score_fn)

    questions_out = []
    for i, q in enumerate(ranked, start=1):
        score = score_fn(q)
        questions_out.append(
            {
                "rank": i,
                "cluster_id": q.cluster_id,
                "text": q.text,
                "batch_count": q.freq,
                "freq": q.freq,
                "score": round(score, 3),
                "confidence": _confidence(q.freq),
                "latest_posted_at": q.latest_posted_at,
                "company_tags": q.company_tags,
                "role_tags": q.role_tags,
                "topic": q.topic,
                "modality_origin": q.modality_origin,
                "variants": q.variants,
                "variant_count": len(q.variants),
                "source_refs": q.source_refs,
            }
        )

    return {
        "role": role,
        "companies": companies,
        "generated_at": ref.isoformat(),
        "recency_window_days": recency_window_days,
        "post_count": post_count,
        "question_count": len(ranked),
        "cluster_count": len(clusters),
        "sources": sources_meta,
        "taxonomy": taxonomy_rows,
        "clusters": clusters,
        "questions": questions_out,
    }


def render_frequency_report(bank: dict, top_n: int = 30) -> str:
    role = bank["role"]
    lines = [
        f"# {role} · 面经题库高频统计",
        "",
        f"生成日期: {bank['generated_at']}",
        f"原始帖数: {bank['post_count']} · 去重后题目: {bank['question_count']} · "
        f"语义簇: {bank.get('cluster_count', bank['question_count'])} · "
        f"时效: 近 {bank.get('recency_window_days', 90)} 天",
        "",
        "## 公司 × 岗位分布",
        "",
        "| 公司 | 岗位 | 题数 | 代表题 |",
        "|---|---|---|---|",
    ]
    for row in bank["taxonomy"][:20]:
        top = (row.get("top_question") or "")[:40]
        if len(row.get("top_question") or "") > 40:
            top += "…"
        lines.append(
            f"| {row['company']} | {row['role']} | {row['question_count']} | {top} |"
        )

    lines.extend(["", f"## 高频题簇 Top {top_n}（按出现批次）", ""])
    for row in bank.get("clusters", bank["questions"])[:top_n]:
        if "representative" in row:
            text = row["representative"]
            batch = row.get("batch_count", row.get("freq", 1))
            variants = row.get("variants") or []
            rank = row.get("rank", "?")
        else:
            text = row["text"]
            batch = row.get("batch_count", row.get("freq", 1))
            variants = row.get("variants") or []
            rank = row.get("rank", "?")
        companies = "、".join(row.get("company_tags") or []) or "未标注"
        lines.append(f"### {rank}. {text}")
        lines.append("")
        lines.append(
            f"- 出现批次: {batch} · 置信: {row.get('confidence', _confidence(batch))} · "
            f"主题: {row.get('topic', '')} · 公司: {companies}"
        )
        if variants:
            lines.append(f"- 同类表述: {'；'.join(variants[:3])}")
        if row.get("latest_posted_at"):
            lines.append(f"- 最近出现: {row['latest_posted_at']}")
        refs = row.get("source_refs") or []
        if refs:
            lines.append(f"- 来源: `{refs[0]}`")
        lines.append("")

    topic_stats: dict[str, int] = {}
    for q in bank["questions"]:
        topic_stats[q["topic"]] = topic_stats.get(q["topic"], 0) + q["freq"]
    lines.extend(["## 主题频次", ""])
    for topic, count in sorted(topic_stats.items(), key=lambda x: -x[1])[:12]:
        lines.append(f"- **{topic}**: {count}")
    lines.append("")
    return "\n".join(lines)
