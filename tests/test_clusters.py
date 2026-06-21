from datetime import date

from scripts.corpus.clusters import assign_cluster_ids, build_clusters
from scripts.corpus.dedupe_rank import _recency_weight
from scripts.models import Question


def test_assign_cluster_ids():
    qs = [Question("A", freq=2), Question("B", freq=1)]
    assign_cluster_ids(qs)
    assert qs[0].cluster_id == "c001"
    assert qs[1].cluster_id == "c002"


def test_build_clusters_ranked_by_batch():
    qs = [
        Question("RAG 怎么优化", freq=3, topic="RAG", variants=["RAG 优化方法"]),
        Question("Agent 记忆", freq=1, topic="Agent"),
    ]
    assign_cluster_ids(qs)
    ref = date(2026, 6, 18)
    clusters = build_clusters(qs, ref_score_fn=lambda q: q.freq * _recency_weight(q.latest_posted_at, ref))
    assert clusters[0]["rank"] == 1
    assert clusters[0]["batch_count"] == 3
    assert clusters[0]["variants"] == ["RAG 优化方法"]
